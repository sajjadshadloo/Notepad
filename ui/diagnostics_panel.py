"""The settings page for inspecting and explicitly exporting diagnostics."""
from datetime import datetime

from PyQt6.QtCore import QTimer, Qt, QUrl, QStandardPaths
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

from core import diagnostics, settings_manager
from core.jalali import to_persian_digits
from ui.background import ReadWorker, start_background
from ui.cloud_sync_worker import OpenLinkWorker
from ui.kit import Button, current_palette, font

LEVELS = {'DEBUG': 'جزئیات', 'INFO': 'اطلاعات', 'WARNING': 'هشدار', 'ERROR': 'خطا', 'CRITICAL': 'بحرانی'}
TITLES = {'session.start': 'برنامه شروع شد', 'session.end': 'برنامه بسته شد',
    'http.started': 'درخواست به سرور ارسال شد', 'http.completed': 'پاسخ سرور دریافت شد',
    'http.rejected': 'سرور درخواست را نپذیرفت', 'http.failed': 'خطای شبکه یا خواندن پاسخ',
    'sync.completed': 'همگام‌سازی پایان یافت', 'sync.failed': 'همگام‌سازی انجام نشد',
    'sync.skipped': 'همگام‌سازی آغاز نشد', 'pairing.waiting': 'در انتظار تأیید تلگرام',
    'pairing.approved': 'تلگرام اتصال را تأیید کرد', 'pairing.retry': 'تلاش دوباره برای اتصال',
    'pairing.failed': 'اتصال تلگرام انجام نشد', 'pairing.stopped': 'انتظار اتصال تمام شد',
    'external.result': 'نتیجهٔ بازکردن برنامهٔ بیرونی', 'external.failed': 'برنامهٔ بیرونی باز نشد',
    'ui.stalled': 'پاسخ‌گویی پنجره متوقف شد', 'operation.started': 'عملیات شروع شد',
    'operation.ended': 'عملیات پایان یافت', 'operation.failed': 'عملیات با خطا متوقف شد',
    'diagnostics.detail': 'وضعیت ثبت جزئیات تغییر کرد', 'file.recycle.failed': 'انتقال به سطل بازیافت انجام نشد',
    'file.read.started': 'خواندن فایل شروع شد', 'file.read.completed': 'خواندن فایل پایان یافت',
    'file.read.failed': 'فایل خوانده نشد', 'file.write.started': 'ذخیرهٔ فایل شروع شد',
    'file.write.completed': 'ذخیرهٔ فایل پایان یافت', 'file.write.failed': 'فایل ذخیره نشد'}
REASONS = {'journal_damaged': 'سابقهٔ همگام‌سازی آسیب دیده است؛ فایل‌ها خودکار تغییر نکرده‌اند.',
    'legacy_journal': 'سابقهٔ قبلی پوشه با اتصال به حساب تازه سازگار نیست.',
    'account_mismatch': 'حساب این پوشه و اتصال فعلی یکسان نیستند.',
    'folder_changed': 'پوشه تغییر کرده و اتصال آن به تأیید دوباره نیاز دارد.',
    'folder_unconfirmed': 'پوشهٔ فعلی هنوز برای همگام‌سازی تأیید نشده است.',
    'duplicate_paths': 'دو مسیر سرور فقط در بزرگی یا کوچکی حروف تفاوت دارند.',
    'remote_path_changed': 'مسیر یادداشت روی سرور به شکل غیرمنتظره تغییر کرده است.',
    'unsafe_path': 'مسیر دریافتی مجاز نیست؛ فایل نوشته نشده است.',
    'unconfigured': 'تنظیمات اتصال یا کلید قابل استفاده کامل نیست.',
    'network_unavailable': 'ارتباط شبکه یا خواندن پاسخ سرور انجام نشد.',
    'version_conflict': 'نسخهٔ یادداشت هم‌زمان در جای دیگری تغییر کرده است.',
    'invalid_pairing_link': 'نشانی دریافت‌شده برای اتصال تلگرام معتبر نیست.',
    'not_approved': 'اتصال هنوز در تلگرام تأیید نشده است.', 'disabled': 'همگام‌سازی خاموش است.'}


def describe_event(event, display=False):
    labels = {'error_type': 'نوع خطا', 'error_chain': 'زنجیرهٔ خطا',
        'os_error': 'کد خطای سیستم', 'tls_verify_code': 'کد خطای گواهی TLS', 'http_status': 'پاسخ HTTP',
        'reason': 'علت مرحله', 'message': 'شرح', 'duration_ms': 'زمان اجرا (ms)',
        'time': 'زمان (UTC)', 'level': 'سطح', 'component': 'بخش', 'event': 'نوع رویداد',
        'operation': 'عملیات', 'operation_id': 'شناسهٔ عملیات', 'request_id': 'شناسهٔ درخواست', 'route': 'مسیر API',
        'method': 'روش درخواست', 'source': 'محل کد', 'thread': 'رشتهٔ اجرا',
        'uploaded': 'ارسال', 'downloaded': 'دریافت', 'deleted': 'حذف', 'conflicts': 'تعارض', 'skipped': 'در انتظار',
        'id': 'شناسهٔ رویداد', 'session': 'شناسهٔ اجرا', 'version': 'نسخه'}
    lines = [f'{label}: ' + (f'\u2068{event[key]}\u2069' if display else str(event[key]))
             for key, label in labels.items() if key in event]
    if event.get('reason') in REASONS:
        lines.insert(0, REASONS[event['reason']] + '\n')
    if event.get('event') in TITLES:
        lines.insert(0, TITLES[event['event']] + '\n')
    if event.get('stack'):
        lines.extend(['', 'مسیر فراخوانی:'] + event['stack'])
    return '\n'.join(lines)


class DiagnosticsPanel(QWidget):
    def __init__(self, version, parent=None):
        super().__init__(parent)
        self._version = version
        self._folder = settings_manager.app_data_dir() / 'logs'
        self._events, self._reader, self._exporter = [], None, None
        self._signature = None
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        self.summary = QLabel('در حال خواندن گزارش‌ها…')
        self.summary.setFont(font(12.5))
        layout.addWidget(self.summary)

        controls = QHBoxLayout()
        self.level = QComboBox()
        for caption, value in [('همهٔ رویدادها', ''), ('خطاها و بحرانی', 'errors'),
                               ('هشدارها', 'WARNING'), ('اطلاعات', 'INFO'), ('جزئیات', 'DEBUG')]:
            self.level.addItem(caption, value)
        self.level.setFont(font(12))
        self.search = QLineEdit()
        self.search.setPlaceholderText('جست‌وجو در شرح، بخش یا شناسه…')
        self.search.setClearButtonEnabled(True)
        self.search.setFont(font(12))
        controls.addWidget(self.level)
        controls.addWidget(self.search, 1)
        self.refresh_button = self._button('تازه‌سازی', self.refresh)
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)

        self.events = QTreeWidget()
        self.events.setHeaderLabels(['زمان', 'سطح', 'بخش', 'شرح رویداد'])
        self.events.setRootIsDecorated(False)
        self.events.setUniformRowHeights(True)
        self.events.setAlternatingRowColors(True)
        self.events.setFont(font(11.5))
        self.events.setFixedHeight(160)
        self.events.setColumnWidth(0, 70)
        self.events.setColumnWidth(1, 60)
        self.events.setColumnWidth(2, 110)
        self.events.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.events.currentItemChanged.connect(self._selected)
        layout.addWidget(self.events)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('یک رویداد را انتخاب کن تا شرح و مسیر خطایش نمایش داده شود.')
        self.details.setFont(font(11.5))
        self.details.setFixedHeight(140)
        self.details.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.details.setMaximumBlockCount(120)
        layout.addWidget(self.details)

        actions = QHBoxLayout()
        self.export_button = self._button('گرفتن گزارش پشتیبانی', self._choose_export, primary=True)
        self.copy_button = self._button('کپی رویداد', self._copy)
        self.copy_button.setEnabled(False)
        actions.addWidget(self.export_button, 1)
        actions.addWidget(self.copy_button)
        actions.addWidget(self._button('پوشهٔ گزارش‌ها', self._open_folder))
        layout.addLayout(actions)
        verbose = QHBoxLayout()
        self.verbose_button = self._button('ثبت جزئیات · ۱۵ دقیقه', self._toggle_verbose)
        self.verbose_state = QLabel()
        self.verbose_state.setFont(font(11.5))
        verbose.addWidget(self.verbose_button)
        verbose.addWidget(self.verbose_state, 1)
        layout.addLayout(verbose)

        self.status = QLabel('گزارش روی همین رایانه می‌ماند؛ ارسال آن فقط با انتخاب خودت انجام می‌شود.')
        self.status.setWordWrap(True)
        self.status.setFont(font(11.5))
        layout.addWidget(self.status)
        t = current_palette()
        self.setStyleSheet(
            f'QLabel {{ color: {t["muted"]}; }}'
            f'QLineEdit, QComboBox, QTreeWidget, QPlainTextEdit {{ background: {t["window"]}; color: {t["text"]};'
            f' border: 1px solid {t["border"]}; border-radius: 6px; padding: 4px; }}'
            f'QHeaderView::section {{ background: {t["surface_alt"]}; color: {t["muted"]}; border: none; padding: 5px; }}'
            f'QTreeWidget {{ alternate-background-color: {t["surface"]}; }}'
            f'QTreeWidget::item:selected {{ background: {t["accent"]}; color: {t["on_accent"]}; }}'
            'QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }'
            f'QScrollBar::handle:vertical {{ background: {t["border"]}; min-height: 24px; border-radius: 4px; }}'
            'QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }'
            'QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }')
        self._search_timer = QTimer(self, singleShot=True, interval=180)
        self._search_timer.timeout.connect(self._fill)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self.level.currentIndexChanged.connect(self._fill)
        self._timer = QTimer(self, interval=2000)
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start()
        self.refresh()

    def _button(self, label, slot, primary=False):
        button = Button(label, None, height=32, radius=7, padding=(10, 10), px=11.5,
            normal={'bg': 'accent' if primary else 'surface_alt', 'fg': 'on_accent' if primary else 'text'},
            hover={'bg': 'accent_hover' if primary else 'divider'})
        button.clicked.connect(slot)
        return button

    def refresh(self):
        self._update_verbose_state()
        if self._reader is not None:
            return
        folder = self._folder
        self._reader = ReadWorker(lambda _: diagnostics.read_events(folder))
        self._reader.completed.connect(self._loaded)
        self._reader.finished.connect(self._reader_finished)
        self.destroyed.connect(self._reader.cancel)
        start_background(self._reader)

    def _auto_refresh(self):
        if self.isVisible():
            self.refresh()

    def _reader_finished(self):
        self._reader = None

    def _loaded(self, events, error):
        if error:
            self.status.setText(error)
            return
        self._events = events
        self._fill()

    def _fill(self, *_):
        needle, level = self.search.text().strip().casefold(), self.level.currentData()
        shown = [event for event in reversed(self._events)
            if (not level or (event['level'] in ('ERROR', 'CRITICAL') if level == 'errors' else event['level'] == level))
            and (not needle or needle in (' '.join(str(v) for v in event.values()) + ' ' + TITLES.get(event.get('event'), '')).casefold())]
        signature = (tuple(event.get('id', event['time']) for event in shown), needle, level)
        errors = sum(event['level'] in ('ERROR', 'CRITICAL') for event in self._events)
        self.summary.setText(to_persian_digits(f'{len(self._events)} رویداد اخیر · {errors} خطا · {len(shown)} مورد در این فیلتر'))
        if signature == self._signature:
            return
        self._signature = signature
        current = self.events.currentItem()
        selected = current.data(0, Qt.ItemDataRole.UserRole).get('id') if current else None
        self.events.clear()
        for event in shown:
            try:
                stamp = datetime.fromisoformat(event['time']).astimezone().strftime('%H:%M:%S')
            except ValueError:
                stamp = '—'
            item = QTreeWidgetItem([to_persian_digits(stamp), LEVELS.get(event['level'], event['level']),
                event.get('component', '').removeprefix('notepad.'),
                TITLES.get(event.get('event'), (event['message'].splitlines() or [''])[0])])
            item.setData(0, Qt.ItemDataRole.UserRole, event)
            item.setToolTip(3, event['message'])
            if event['level'] in ('ERROR', 'CRITICAL'):
                item.setForeground(1, QColor(current_palette()['danger']))
            self.events.addTopLevelItem(item)
            if selected and event.get('id') == selected:
                self.events.setCurrentItem(item)

    def _selected(self, item, _previous):
        self.copy_button.setEnabled(item is not None)
        self.details.setPlainText(describe_event(item.data(0, Qt.ItemDataRole.UserRole), display=True) if item else '')

    def _copy(self):
        if self.events.currentItem():
            event = self.events.currentItem().data(0, Qt.ItemDataRole.UserRole)
            QApplication.clipboard().setText(describe_event(event))

    def _update_verbose_state(self):
        service = diagnostics.runtime()
        seconds = service.verbose_remaining() if service else 0
        self.verbose_button.setEnabled(service is not None)
        self.verbose_button.setText('خاموش‌کردن جزئیات' if seconds else 'ثبت جزئیات · ۱۵ دقیقه')
        self.verbose_state.setText(to_persian_digits(f'فعال · {seconds // 60:02}:{seconds % 60:02} باقی‌مانده') if seconds
                                   else 'ثبت عادی روشن؛ جزئیات بیشتر خاموش')
        if service and (service.dropped or service.write_errors):
            self.status.setText(f'گزارش‌های ثبت‌نشده: {service.dropped} · خطای نوشتن گزارش: {service.write_errors}')

    def _toggle_verbose(self):
        service = diagnostics.runtime()
        if service:
            service.set_verbose(not bool(service.verbose_remaining()))
            self._update_verbose_state()
            self.refresh()

    def _choose_export(self):
        if self._exporter is not None:
            return
        from pathlib import Path

        downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        dialog = QFileDialog(self, 'ذخیرهٔ گزارش پشتیبانی',
            str(Path(downloads) / f'NotepadPlus-Report-{datetime.now():%Y%m%d-%H%M%S}.zip'), 'Diagnostic report (*.zip)')
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix('zip')
        if dialog.exec() and dialog.selectedFiles():
            filename = dialog.selectedFiles()[0]
            if not filename.lower().endswith('.zip'):
                self.status.setText('برای گزارش پشتیبانی، پسوند zip را انتخاب کن.')
                return
            self.export_to(filename)

    def export_to(self, filename):
        if self._exporter is not None:
            return
        version = self._version
        self.export_button.setEnabled(False)
        self.status.setText('در حال آماده‌کردن گزارش؛ می‌توانی به کار با برنامه ادامه بدهی…')
        self._exporter = ReadWorker(lambda _: diagnostics.export_report(filename, version))
        self._exporter.completed.connect(self._exported)
        self._exporter.finished.connect(self._export_finished)
        start_background(self._exporter)

    def _exported(self, count, error):
        self.status.setText('ساخت گزارش انجام نشد؛ مسیر ذخیره و فضای دیسک را بررسی کن.' if error else
            to_persian_digits(f'گزارش پشتیبانی با {count} رویداد ذخیره شد. یادداشت‌ها و کلیدهای اتصال در آن نیستند.'))

    def _export_finished(self):
        self._exporter = None
        self.export_button.setEnabled(True)

    def _open_folder(self):
        link = QUrl.fromLocalFile(str(self._folder)).toString()
        start_background(OpenLinkWorker(link))
