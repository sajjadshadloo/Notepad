"""Run network and disk sync away from the Qt event loop."""

import logging
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.cloud_sync import CloudApi, SyncError, sync_once
from core.cloud_sync_status import record_sync_status
from core.diagnostics import traced

log = logging.getLogger(__name__)


class CloudSyncWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, root: str, state_file: Path, url: str, key: str,
                 protected: set[str], parent=None, proxy: str = "", user_id: str = "", excluded_paths=()):
        super().__init__(parent)
        self.proxy = proxy
        self.root = Path(root)
        self.state_file = state_file
        self.url = url
        self.key = key
        self.protected = protected
        self.user_id = user_id
        self.excluded_paths = excluded_paths

    @traced('sync')
    def run(self):
        api = None
        try:
            api = CloudApi(self.url, self.key, self.proxy)
            api.account_id = self.user_id
            if self.user_id and api.call('/account').get('user_id') != self.user_id:
                raise SyncError("حساب سرور با اتصال این پوشه هم‌خوان نیست؛ هیچ فایلی تغییر نکرد.", code="account_mismatch")
            result = sync_once(self.root, self.state_file, api, self.protected, self.excluded_paths)
            log.info('Sync pass completed', extra={'event': 'sync.completed', **asdict(result)})
            self._record_status(api, result)
            self.completed.emit(result, "")
        except Exception as exc:
            log.error('Sync pass failed', exc_info=True, extra={'event': 'sync.failed'})
            self._record_status(api, error=str(exc))
            self.completed.emit(None, str(exc))

    def _record_status(self, api, result=None, error=""):
        try:
            record_sync_status(self.state_file.with_name("cloud_sync_status.json"), api, result, error)
        except OSError:
            # Even a full/locked status folder must release the busy indicator.
            log.warning("Could not record sync status", exc_info=True)


class SettingsTest(QThread):
    """The server and bot checks behind «ذخیره و تست», off the UI thread."""

    done = pyqtSignal(bool, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    @traced('connection.test')
    def run(self):
        from core import cloud_config

        try:
            ok, message = cloud_config.check_all(self.settings)
        except Exception:
            log.error('Connection settings test failed', exc_info=True, extra={'event': 'connection.test.failed'})
            ok, message = False, "تست انجام نشد. دوباره امتحان کن."
        log.info('Connection settings test ended', extra={'event': 'connection.test.result', 'reason': 'ok' if ok else 'failed'})
        self.done.emit(ok, message)


class PairingWorker(QThread):
    ready = pyqtSignal(object)
    progress = pyqtSignal(str)
    done = pyqtSignal(object, str)

    def __init__(self, settings, root, excluded_paths, parent=None):
        super().__init__(parent)
        self.settings, self.root, self.excluded_paths = settings, root, excluded_paths

    @traced('pairing')
    def run(self):
        import time
        from core import cloud_pairing

        try:
            attempt = cloud_pairing.begin(self.settings.proxy)
            log.info('Pairing request created; waiting for Telegram confirmation', extra={'event': 'pairing.waiting'})
            self.ready.emit({"telegram_url": attempt.telegram_url, "confirm_code": attempt.confirm_code})
            while not self.isInterruptionRequested() and time.time() * 1000 < attempt.expires_at:
                try:
                    result = cloud_pairing.poll(attempt, self.settings.proxy)
                except SyncError as exc:
                    if exc.status not in (None, 408, 429, 500, 502, 503, 504):
                        raise
                    log.warning('Pairing temporarily unavailable; retrying the same request',
                        extra={'event': 'pairing.retry', 'http_status': exc.status, 'error_type': type(exc).__name__})
                    self.progress.emit("ارتباط با سرور قطع شد؛ با همان کد دوباره بررسی می‌کنم…")
                    self._pause(5)
                    continue
                if self.isInterruptionRequested():
                    break
                if result.get("status") == "approved":
                    settings = cloud_pairing.connected_settings(attempt, result, self.settings, self.root, self.excluded_paths)
                    log.info('Telegram approved this device', extra={'event': 'pairing.approved'})
                    self.done.emit(settings, "")
                    return
                self.progress.emit("منتظر تأیید همین کد در تلگرام… برنامه قابل استفاده است.")
                self._pause(3)
            log.info('Pairing ended without approval', extra={'event': 'pairing.stopped',
                'reason': 'cancelled' if self.isInterruptionRequested() else 'expired'})
            self.done.emit(None, "اتصال لغو شد یا زمان آن تمام شد. دوباره شروع کن.")
        except Exception as exc:
            log.error('Pairing failed', exc_info=True, extra={'event': 'pairing.failed', 'http_status': getattr(exc, 'status', None)})
            code = getattr(exc, "status", None)
            message = {410: "زمان اتصال تمام شد. دوباره شروع کن.",
                       429: "درخواست زیاد است. یک دقیقه بعد دوباره امتحان کن.",
                       503: "سرویس اتصال فعلاً آماده نیست. کمی بعد دوباره امتحان کن."}.get(code)
            self.done.emit(None, message or (str(exc) if isinstance(exc, SyncError) else "اتصال انجام نشد. اینترنت و تلگرام را بررسی کن."))

    def _pause(self, seconds):
        for _ in range(seconds * 5):
            if self.isInterruptionRequested():
                break
            self.msleep(200)


class OpenLinkWorker(QThread):
    done = pyqtSignal(str, bool)

    def __init__(self, link):
        super().__init__()
        self.link = link

    @traced('external.open')
    def run(self):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        try:
            opened = QDesktopServices.openUrl(QUrl(self.link))
        except Exception:
            log.warning('External application launch failed', exc_info=True, extra={'event': 'external.failed'})
            opened = False
        log.info('External application launch request ended', extra={'event': 'external.result',
            'reason': 'accepted' if opened else 'refused'})
        self.done.emit(self.link, opened)


class DisconnectWorker(QThread):
    done = pyqtSignal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    @traced('device.disconnect')
    def run(self):
        try:
            s = self.settings
            CloudApi(s.url, s.key, s.proxy).call('/devices/' + s.device_id, 'DELETE')
            self.done.emit(True)
        except Exception:
            log.error('Device revocation failed', exc_info=True, extra={'event': 'device.disconnect.failed'})
            self.done.emit(False)
