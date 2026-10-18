"""Application-owned update jobs survive closing or rebuilding Settings."""
import logging
import sys
from time import time

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QMessageBox,
                            QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget)

from core import app_updates as updates, settings_manager
from core.jalali import to_persian_digits
from ui.background import start_background
from ui.cloud_sync_worker import OpenLinkWorker
from ui.kit import Button, current_palette, font

log = logging.getLogger(__name__)


class UpdateWorker(QThread):
    completed = pyqtSignal(object, str)
    progress = pyqtSignal(int, int)

    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        try:
            result = self.task(self.isInterruptionRequested, self.progress.emit)
            self.completed.emit(result, '')
        except updates.Cancelled as exc:
            self.completed.emit(None, str(exc))
        except updates.UpdateError as exc:
            log.warning('Application update operation failed', exc_info=True,
                        extra={'event': 'update.failed'})
            self.completed.emit(None, str(exc))
        except Exception:
            log.exception('Unexpected application updater failure', extra={'event': 'update.failed'})
            self.completed.emit(None, 'به‌روزرسانی انجام نشد؛ گزارش عیب‌یابی را بررسی کن.')


class UpdateController(QObject):
    changed = pyqtSignal()
    available = pyqtSignal(str)
    install_requested = pyqtSignal(object)

    def __init__(self, version, config, parent=None):
        super().__init__(parent)
        self.version, self.config = version, config
        self.folder = settings_manager.app_data_dir() / 'updates'
        self.phase, self.message = 'idle', 'برای بررسی نسخهٔ جدید، «بررسی الان» را بزن.'
        self.release = self.downloaded = self.pending_install = self._worker = None
        self.done = self.total = 0
        self._stopping = False
        self.timer = QTimer(self, interval=60 * 60 * 1000)
        self.timer.timeout.connect(self.auto_check)
        # Source runs and packaging smoke tests must never contact GitHub.
        if getattr(sys, 'frozen', False) and '--smoke-test' not in sys.argv:
            self.timer.start()
            QTimer.singleShot(15_000, self.auto_check)

    @property
    def busy(self):
        return self._worker is not None

    @property
    def automatic(self):
        return bool(self.config.get('check_app_updates', True))

    def set_automatic(self, enabled):
        self.config['check_app_updates'] = bool(enabled)
        settings_manager.save(self.config)
        self.changed.emit()

    def auto_check(self):
        if (not self._stopping and self.automatic and not self.busy
                and updates.check_due(self.config.get('last_app_update_check', 0))):
            self.check()

    def _start(self, phase, message, task):
        if self.busy or self._stopping:
            return False
        self.phase, self.message = phase, message
        worker = UpdateWorker(task)
        self._worker = worker
        worker.progress.connect(self._progress)
        worker.completed.connect(lambda result, error: self._completed(phase, result, error))
        worker.finished.connect(self._finished)
        start_background(worker)
        self.changed.emit()
        return True

    def _finished(self):
        self._worker = None
        self.changed.emit()

    def check(self):
        if self.busy or self._stopping:
            return
        self.release = self.downloaded = None
        self.config['last_app_update_check'] = time()
        settings_manager.save(self.config)
        self._start('checking', 'در حال بررسی نسخهٔ منتشرشده…',
                    lambda cancel, progress: updates.check_latest(self.version, cancel))

    def download(self):
        if self.release is None or self.busy:
            return
        self.done, self.total = 0, self.release.size
        release = self.release
        self._start('downloading', 'در حال دریافت نسخهٔ جدید…',
                    lambda cancel, progress: updates.download_release(release, self.folder, progress, cancel))

    def cancel(self):
        if self._worker is not None:
            self._worker.requestInterruption()
            self.message = 'در حال لغو؛ منتظر پایان درخواست شبکه…'
            self.changed.emit()

    def install(self):
        if self.downloaded is None or self.busy:
            return
        downloaded = self.downloaded
        self._start('verifying', 'در حال کنترل نهایی فایل نصب…',
                    lambda cancel, progress: updates.verify_download(downloaded, self.folder, cancel))

    def _progress(self, done, total):
        self.done, self.total = done, total
        self.changed.emit()

    def _completed(self, phase, result, error):
        if self._stopping:
            return
        if error:
            self.phase, self.message = 'error', error
            if phase == 'verifying':
                self.downloaded = None
        elif phase == 'checking':
            self.release = result
            self.phase = 'available' if result else 'current'
            self.message = ('نسخهٔ ' + to_persian_digits(result.version) + ' آمادهٔ دریافت است.'
                            if result else 'نسخهٔ جدیدتری از نسخهٔ فعلی منتشر نشده است.')
            if result:
                self.available.emit(result.version)
        elif phase == 'downloading':
            self.downloaded = result
            self.phase, self.message = 'ready', 'دریافت و کنترل صحت تمام شد؛ آمادهٔ نصب است.'
        elif phase == 'verifying':
            self.phase, self.message = 'ready', 'نصاب تأیید شد؛ در انتظار بستن امن برنامه.'
            self.install_requested.emit(result)
        self.changed.emit()

    def stop(self):
        self._stopping = True
        self.timer.stop()
        if self._worker is not None:
            self._worker.requestInterruption()
            # Network timeout is 10 seconds; cancel is checked before every read.
            # Retention in ui.background covers a platform call that exceeds it.
            self._worker.wait(12_000)


class UpdatesPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._opener = None
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)
        current = QLabel('نسخهٔ نصب‌شده: ' + to_persian_digits(controller.version))
        current.setFont(font(14, 600))
        layout.addWidget(current)
        self.automatic = QCheckBox('بررسی خودکار نسخهٔ جدید، روزی یک‌بار')
        self.automatic.setFont(font(12))
        self.automatic.toggled.connect(controller.set_automatic)
        layout.addWidget(self.automatic)
        hint = QLabel('دریافت و نصب فقط با انتخاب تو انجام می‌شود. بررسی نسخه مستقل از اتصال تلگرام است.')
        hint.setFont(font(11.5))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setFont(font(12.5))
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText('توضیح تغییرات نسخهٔ جدید اینجا نمایش داده می‌شود.')
        self.notes.setFont(font(12))
        self.notes.setMinimumHeight(120)
        self.notes.setMaximumHeight(200)
        layout.addWidget(self.notes)
        row = QHBoxLayout()
        self.check_button = self._button('بررسی الان', controller.check)
        self.download_button = self._button('دریافت نسخهٔ جدید', controller.download, True)
        self.install_button = self._button('نصب و بازکردن دوباره', self._install, True)
        self.cancel_button = self._button('لغو دریافت', controller.cancel)
        self.releases_button = self._button('صفحهٔ نسخه‌ها', self._open_releases)
        for button in (self.check_button, self.download_button, self.install_button, self.cancel_button,
                       self.releases_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.footer = QLabel('قبل از نصب، برنامه برای ذخیرهٔ تغییرات باز از تو سؤال می‌کند. لغو خروج، نصب را متوقف می‌کند.')
        self.footer.setFont(font(11.5))
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)
        if not getattr(sys, 'frozen', False) or sys.platform != 'win32':
            self.footer.setText('نصب خودکار در نسخهٔ نصب‌شدهٔ ویندوز فعال است؛ این اجرا از سورس است.')
        t = current_palette()
        self.setStyleSheet(f'QLabel, QCheckBox {{ color: {t["muted"]}; }}'
            f'QPlainTextEdit {{ background: {t["window"]}; color: {t["text"]}; border: 1px solid {t["border"]};'
            ' border-radius: 7px; padding: 8px; }'
            f'QProgressBar {{ border: 1px solid {t["border"]}; border-radius: 5px; text-align: center; color: {t["text"]}; }}'
            f'QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 4px; }}')
        controller.changed.connect(self.refresh)
        self.refresh()

    def _button(self, text, callback, primary=False):
        button = Button(text, None, height=34, radius=7, padding=(10, 10), px=11.5,
            normal={'bg': 'accent' if primary else 'surface_alt', 'fg': 'on_accent' if primary else 'text'},
            hover={'bg': 'accent_hover' if primary else 'divider'})
        button.clicked.connect(callback)
        return button

    def refresh(self):
        c = self.controller
        self.automatic.blockSignals(True)
        self.automatic.setChecked(c.automatic)
        self.automatic.blockSignals(False)
        self.status.setText(c.message)
        self.check_button.setEnabled(not c.busy)
        self.download_button.setVisible(c.release is not None and c.downloaded is None)
        self.download_button.setEnabled(not c.busy)
        self.install_button.setVisible(c.downloaded is not None)
        self.install_button.setEnabled(not c.busy and getattr(sys, 'frozen', False) and sys.platform == 'win32')
        self.cancel_button.setVisible(c.busy and c.phase in ('checking', 'downloading'))
        self.cancel_button.setText('لغو بررسی' if c.phase == 'checking' else 'لغو دریافت')
        self.progress.setVisible(c.phase == 'downloading')
        self.progress.setValue(c.done * 100 // c.total if c.total else 0)
        notes = c.release.notes if c.release else ''
        if self.notes.toPlainText() != notes:
            self.notes.setPlainText(notes)

    def _install(self):
        answer = QMessageBox.question(self, 'نصب به‌روزرسانی',
            'برنامه بسته می‌شود و نسخهٔ جدید نصب خواهد شد. ادامه می‌دهی؟',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.install()

    def _open_releases(self):
        if self._opener is not None and self._opener.isRunning():
            return
        self._opener = OpenLinkWorker(updates.RELEASES_URL)
        self._opener.done.connect(self._releases_opened)
        start_background(self._opener)

    def _releases_opened(self, link, opened):
        if not opened:
            self.footer.setText('صفحه باز نشد؛ این نشانی را در مرورگر باز کن: ' + updates.RELEASES_URL)
