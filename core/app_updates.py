"""Small, bounded GitHub release updater; no Qt and no application credentials."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from time import monotonic, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

log = logging.getLogger(__name__)
REPOSITORY = 'sajjadshadloo/Notepad'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
CHECK_INTERVAL = 24 * 60 * 60
MAX_INSTALLER = 256 * 1024 * 1024
_VERSION = re.compile(r'v?(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\Z')
_HASH = re.compile(r'[0-9a-fA-F]{64}\Z')


class UpdateError(Exception):
    """A constant user-facing message, never an HTTP body or credential."""


class Cancelled(UpdateError):
    def __init__(self):
        super().__init__('دریافت به‌روزرسانی لغو شد.')


def version_tuple(value):
    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise UpdateError('شمارهٔ نسخهٔ منتشرشده معتبر نیست.')
    return tuple(map(int, match.groups()))


def check_due(last_attempt, now=None):
    now = time() if now is None else now
    try:
        age = now - float(last_attempt)
        return age < 0 or age >= CHECK_INTERVAL
    except (TypeError, ValueError):
        return True


def _safe_transport(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and not parsed.fragment
            and parsed.hostname in ('api.github.com', 'github.com',
                'release-assets.githubusercontent.com', 'objects.githubusercontent.com'))


class _Redirects(HTTPRedirectHandler):
    def __init__(self, deadline, cancelled):
        self.deadline, self.cancelled = deadline, cancelled

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _continue(self.cancelled, self.deadline)
        if not _safe_transport(newurl):
            raise UpdateError('مقصد دانلود به‌روزرسانی مورد تأیید نیست.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _continue(cancelled, deadline):
    if cancelled():
        raise Cancelled()
    if monotonic() >= deadline:
        raise UpdateError('زمان دریافت به‌روزرسانی تمام شد؛ دوباره تلاش کن.')


def _open(url, cancelled, deadline):
    _continue(cancelled, deadline)
    if not _safe_transport(url):
        raise UpdateError('نشانی به‌روزرسانی مورد تأیید نیست.')
    request = Request(url, headers={'User-Agent': 'NotepadPlus-Updater',
        'Accept': 'application/vnd.github+json' if url == API_URL else 'application/octet-stream'})
    # System proxy and normal certificate verification are deliberately retained.
    return build_opener(_Redirects(deadline, cancelled)).open(request, timeout=10)


def _small_download(url, limit, cancelled, deadline):
    with _open(url, cancelled, deadline) as response:
        chunks, size = [], 0
        while True:
            _continue(cancelled, deadline)
            # read1 returns after one socket read so slow trickling responses
            # cannot postpone cancellation until the entire body arrives.
            block = response.read1(min(32 * 1024, limit + 1 - size))
            _continue(cancelled, deadline)
            if not block:
                return b''.join(chunks)
            size += len(block)
            if size > limit:
                raise UpdateError('پاسخ سرویس به‌روزرسانی بیش از حد بزرگ است.')
            chunks.append(block)


def _asset_url(asset, tag, name):
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    if asset.get('browser_download_url') != expected or asset.get('state') != 'uploaded':
        raise UpdateError('فایل نسخهٔ جدید از منبع تأییدشده نیست.')
    return expected


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    size: int
    sha256: str

    @property
    def filename(self):
        return f'NotepadPlus-Setup-{self.version}.exe'


@dataclass(frozen=True)
class DownloadedUpdate:
    release: Release
    path: Path


def check_latest(current, cancelled=lambda: False):
    """None means current/newer; 404 means no public stable release yet."""
    deadline = monotonic() + 40
    try:
        raw = _small_download(API_URL, 512 * 1024, cancelled, deadline)
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
            raise UpdateError('اطلاعات نسخهٔ منتشرشده معتبر نیست.')
        tag = data.get('tag_name')
        latest = version_tuple(tag)
        if latest <= version_tuple(current):
            return None
        version = '.'.join(map(str, latest))
        name = f'NotepadPlus-Setup-{version}.exe'
        assets = data.get('assets', [])
        if not isinstance(assets, list):
            raise UpdateError('فهرست فایل‌های نسخهٔ جدید معتبر نیست.')
        matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name]
        if len(matches) != 1:
            raise UpdateError('نصاب نسخهٔ جدید هنوز آمادهٔ دریافت نیست.')
        asset = matches[0]
        url = _asset_url(asset, tag, name)
        size = asset.get('size')
        if type(size) is not int or not 0 < size <= MAX_INSTALLER:
            raise UpdateError('اندازهٔ نصاب نسخهٔ جدید معتبر نیست.')
        digest = asset.get('digest') or ''
        if isinstance(digest, str) and digest.startswith('sha256:') and _HASH.fullmatch(digest[7:]):
            digest = digest[7:].lower()
        else:
            sums = [a for a in assets if isinstance(a, dict) and a.get('name') == name + '.sha256']
            if len(sums) != 1:
                raise UpdateError('اطلاعات کنترل صحت نسخهٔ جدید منتشر نشده است.')
            checksum_url = _asset_url(sums[0], tag, name + '.sha256')
            checksum = _small_download(checksum_url, 4096, cancelled, deadline).decode('utf-8-sig').strip()
            match = re.fullmatch(r'([0-9a-fA-F]{64})[ \t]+\*?' + re.escape(name), checksum)
            if not match:
                raise UpdateError('اطلاعات کنترل صحت نصاب معتبر نیست.')
            digest = match[1].lower()
        notes = data.get('body') or 'توضیح تغییرات برای این نسخه منتشر نشده است.'
        if not isinstance(notes, str):
            raise UpdateError('توضیح نسخهٔ جدید معتبر نیست.')
        log.info('A newer application release is available', extra={'event': 'update.available'})
        return Release(version, notes[:12000], url, size, digest)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('هنوز نسخهٔ عمومی قابل دریافت پیدا نشد؛ می‌توانی بعداً دوباره بررسی کنی.') from exc
        raise UpdateError('سرویس بررسی نسخه فعلاً پاسخ نمی‌دهد؛ بعداً دوباره تلاش کن.') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError('ارتباط با سرویس به‌روزرسانی برقرار نشد؛ اینترنت را بررسی کن.') from exc
    except (ValueError, UnicodeError, TypeError) as exc:
        raise UpdateError('اطلاعات دریافتی نسخهٔ جدید قابل استفاده نیست.') from exc


def _verify(path, release, cancelled=lambda: False):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != release.size:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(128 * 1024), b''):
            if cancelled():
                raise Cancelled()
            digest.update(block)
    return hmac.compare_digest(digest.hexdigest(), release.sha256)


def download_release(release, folder, progress=lambda done, total: None, cancelled=lambda: False):
    """Stream to a private temporary file; only rename after size/hash checks."""
    version_tuple(release.version)
    if not _HASH.fullmatch(release.sha256) or not 0 < release.size <= MAX_INSTALLER:
        raise UpdateError('اطلاعات نصاب معتبر نیست.')
    expected_url = f'https://github.com/{REPOSITORY}/releases/download/'
    if release.url not in (expected_url + release.version + '/' + release.filename,
                          expected_url + 'v' + release.version + '/' + release.filename):
        raise UpdateError('نشانی نصاب مورد تأیید نیست.')
    folder = Path(folder)
    part = None
    deadline = monotonic() + 300
    try:
        _continue(cancelled, deadline)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / release.filename
        if _verify(destination, release, cancelled):
            progress(release.size, release.size)
            return DownloadedUpdate(release, destination)
        with tempfile.NamedTemporaryFile(dir=folder, prefix='download-', suffix='.part', delete=False) as stream:
            part = Path(stream.name)
            digest, size, percent = hashlib.sha256(), 0, -1
            with _open(release.url, cancelled, deadline) as response:
                while True:
                    _continue(cancelled, deadline)
                    block = response.read1(128 * 1024)
                    _continue(cancelled, deadline)
                    if not block:
                        break
                    size += len(block)
                    if size > release.size:
                        raise UpdateError('اندازهٔ فایل دانلودشده با نسخهٔ منتشرشده یکسان نیست.')
                    stream.write(block)
                    digest.update(block)
                    new_percent = size * 100 // release.size
                    if new_percent != percent:
                        percent = new_percent
                        progress(size, release.size)
            if size != release.size or not hmac.compare_digest(digest.hexdigest(), release.sha256):
                raise UpdateError('کنترل صحت دانلود موفق نبود؛ فایل نصب اجرا نشد. دوباره دریافت کن.')
        os.replace(part, destination)
        part = None
        # Keep at most the current installer and one previous cache entry.
        old = sorted((p for p in folder.glob('NotepadPlus-Setup-*.exe')
                      if p != destination and re.fullmatch(r'NotepadPlus-Setup-\d+\.\d+\.\d+\.exe', p.name)),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for cached in old[1:]:
            try:
                cached.unlink()
            except OSError:
                pass
        log.info('Application update downloaded and verified', extra={'event': 'update.downloaded'})
        return DownloadedUpdate(release, destination)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise UpdateError('دریافت یا ذخیرهٔ نصاب انجام نشد؛ اینترنت و فضای دیسک را بررسی کن.') from exc
    finally:
        if part is not None:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                log.warning('Could not remove partial application download',
                            extra={'event': 'update.cleanup_failed'})


def verify_download(update, folder, cancelled=lambda: False):
    """Recheck immediately before installation, including containment."""
    expected = Path(folder).resolve() / update.release.filename
    if update.path.resolve() != expected or not _verify(update.path, update.release, cancelled):
        raise UpdateError('فایل نصاب تغییر کرده یا در دسترس نیست؛ دوباره دریافت کن.')
    return update


def launch_installer(update, folder):
    """Called only after the main event loop has exited normally."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise UpdateError('نصب به‌روزرسانی از داخل نسخهٔ نصب‌شدهٔ ویندوز انجام می‌شود.')
    verify_download(update, folder)
    executable = Path(sys.executable).resolve()
    if executable.name.lower() != 'notepadplus.exe':
        raise UpdateError('مسیر اجرای برنامه برای نصب به‌روزرسانی معتبر نیست.')
    # Argument list, no shell; never execute remote release text/parameters.
    subprocess.Popen([str(update.path), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                      '/NOTEPADUPDATE=1', f'/DIR={executable.parent}'],
                     cwd=str(update.path.parent), close_fds=True)
    log.info('Update installer started after editor exit', extra={'event': 'update.install_started'})
