import codecs
import os
import logging
import uuid
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def replace_with_retry(source, target, attempts: int = 6, first_delay: float = 0.05):
    """os.replace with a short backoff when Windows reports the file in use.

    Antivirus and search-indexer processes routinely hold freshly written
    files open for a moment; without retries that surfaces as WinError 32/5.
    """
    delay = first_delay
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            if attempt == attempts - 1 or getattr(exc, "winerror", None) not in (5, 32):
                raise
        time.sleep(delay)
        delay *= 2


@dataclass(frozen=True)
class LoadedFile:
    text: str
    encoding: str


def read_text_file(path: str | Path) -> LoadedFile:
    started = time.monotonic()
    fields = {'request_id': str(uuid.uuid4()), 'operation': 'file.read'}
    log.debug('File read started', extra={'event': 'file.read.started', **fields})
    try:
        result = _read_text_file(path)
    except Exception:
        log.error('File read failed', exc_info=True, extra={'event': 'file.read.failed', **fields,
            'duration_ms': (time.monotonic() - started) * 1000})
        raise
    log.debug('File read completed', extra={'event': 'file.read.completed', **fields,
        'duration_ms': (time.monotonic() - started) * 1000, 'count': len(result.text)})
    return result


def _read_text_file(path: str | Path) -> LoadedFile:
    raw = Path(path).read_bytes()

    if raw.startswith(codecs.BOM_UTF8):
        return LoadedFile(raw.decode("utf-8-sig"), "utf-8-sig")
    if raw.startswith(codecs.BOM_UTF16_LE):
        return LoadedFile(raw[len(codecs.BOM_UTF16_LE):].decode("utf-16-le"), "utf-16-le")
    if raw.startswith(codecs.BOM_UTF16_BE):
        return LoadedFile(raw[len(codecs.BOM_UTF16_BE):].decode("utf-16-be"), "utf-16-be")

    for encoding in ("utf-8", "cp1256", "cp1252"):
        try:
            return LoadedFile(raw.decode(encoding), encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("رمزگذاری فایل قابل تشخیص نیست.")


def _encode_text(text: str, encoding: str) -> bytes:
    if encoding == "utf-8-sig":
        return text.encode("utf-8-sig")
    if encoding == "utf-16-le":
        return codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    if encoding == "utf-16-be":
        return codecs.BOM_UTF16_BE + text.encode("utf-16-be")
    return text.encode(encoding)


def write_text_file_atomic(path: str | Path, text: str, encoding: str = "utf-8"):
    started = time.monotonic()
    fields = {'request_id': str(uuid.uuid4()), 'operation': 'file.write'}
    log.debug('Atomic file write started', extra={'event': 'file.write.started', **fields})
    try:
        _write_text_file_atomic(path, text, encoding)
    except Exception:
        log.error('Atomic file write failed', exc_info=True, extra={'event': 'file.write.failed', **fields,
            'duration_ms': (time.monotonic() - started) * 1000})
        raise
    log.debug('Atomic file write completed', extra={'event': 'file.write.completed', **fields,
        'duration_ms': (time.monotonic() - started) * 1000, 'count': len(text)})


def _write_text_file_atomic(path: str | Path, text: str, encoding: str = "utf-8"):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _encode_text(text, encoding)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            os.chmod(temp_name, target.stat().st_mode)
        replace_with_retry(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
