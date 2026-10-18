"""Bounded, private diagnostic events and an explicitly exported support report."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import os
import platform
import queue
import re
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core import settings_manager

MAX_BYTES = 1_000_000
BACKUPS = 2
VIEW_LIMIT = 500
DEBUG_SECONDS = 15 * 60
FILE_NAME = 'diagnostics.jsonl'
_runtime = None
_operation = ContextVar('diagnostic_operation', default=None)


@contextmanager
def operation(name, level=logging.INFO):
    token = _operation.set((name, str(uuid.uuid4())))
    started = time.monotonic()
    logger = logging.getLogger('notepad.operations')
    logger.log(level, 'Operation started', extra={'event': 'operation.started'})
    try:
        yield
    except Exception:
        logger.error('Operation failed', exc_info=True, extra={'event': 'operation.failed',
            'duration_ms': (time.monotonic() - started) * 1000})
        raise
    else:
        logger.log(level, 'Operation ended', extra={'event': 'operation.ended',
            'duration_ms': (time.monotonic() - started) * 1000})
    finally:
        _operation.reset(token)


def traced(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with operation(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def redact(value) -> str:
    text = str(value)[:16000]
    text = re.sub(r'https?://[^\s<>"\']+', '[URL]', text, flags=re.I)
    text = re.sub(r'(?i)\b(?:bearer\s+|dpapi:)[A-Za-z0-9_+/=:.\-]+', '[SECRET]', text)
    text = re.sub(r'\b\d{5,}:[A-Za-z0-9_-]{20,}\b', '[BOT_TOKEN]', text)
    text = re.sub(r'\b[0-9a-fA-F]{32,}\b', '[SECRET]', text)
    text = re.sub(r'''(?ix)\b(?:password|token|poll_key|key_hash|authorization|secret|api_key|key)\b
        ["']?\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,"'}]+)''', '[SECRET]', text)
    text = re.sub(r'(?:[A-Za-z]:[\\/]|\\\\)[^\r\n"\']+', '[PATH]', text)
    text = re.sub(r'(?<!\w)/(?:home|Users|tmp|var|mnt|opt)/[^\s"\']+', '[PATH]', text)
    return text


def _frames(tb):
    result = []
    while tb is not None and len(result) < 30:
        code = tb.tb_frame.f_code
        result.append(f'{Path(code.co_filename).name}:{tb.tb_lineno} in {code.co_name}')
        tb = tb.tb_next
    return result


def event_from_record(record, version, session):
    # Historical merge messages contain note fragments. Keep that local legacy
    # log behaviour separate; no fragment enters the diagnostic report.
    if record.name == 'notepad.cloud_sync' and str(record.msg).startswith('Merged '):
        message = 'Overlapping note edits merged; document contents omitted.'
    elif str(record.msg).startswith('flash before the toast exists:'):
        message = 'A notification was requested before the interface was ready.'
    elif record.name == 'notepad.responsiveness':
        message = str(record.getMessage()).splitlines()[0]
    else:
        message = record.getMessage()
    event = {
        'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
        'level': record.levelname, 'component': record.name[:100],
        'message': redact(message), 'event': redact(getattr(record, 'event', 'log'))[:100],
        'id': str(uuid.uuid4()), 'session': session, 'version': version,
        'thread': redact(record.threadName)[:80],
        'source': f'{Path(record.pathname).name}:{record.lineno} in {record.funcName}',
    }
    context = _operation.get()
    if context:
        event['operation'], event['operation_id'] = context
    for key in ('operation', 'request_id', 'route', 'method', 'reason', 'error_type'):
        value = getattr(record, key, None)
        if isinstance(value, str):
            event[key] = redact(value)[:160]
    for key in ('duration_ms', 'http_status', 'uploaded', 'downloaded', 'deleted', 'conflicts', 'skipped', 'count'):
        value = getattr(record, key, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            event[key] = round(value, 2)
    if record.exc_info and record.exc_info[0]:
        event['error_type'] = record.exc_info[0].__name__
        event['stack'] = _frames(record.exc_info[2])
        code = getattr(record.exc_info[1], 'diagnostic_code', None)
        if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,60}', code):
            event['reason'] = code
        error, seen, chain = record.exc_info[1], set(), []
        while isinstance(error, BaseException) and id(error) not in seen and len(chain) < 5:
            seen.add(id(error))
            chain.append(type(error).__name__)
            for attr in ('errno', 'winerror', 'verify_code'):
                code = getattr(error, attr, None)
                if isinstance(code, int):
                    event['os_error' if attr in ('winerror', 'errno') else 'tls_verify_code'] = code
            reason = getattr(error, 'reason', None)
            error = reason if isinstance(reason, BaseException) else error.__cause__ or error.__context__
        event['error_chain'] = chain
    stack = getattr(record, 'diagnostic_stack', None)
    if isinstance(stack, list):
        event['stack'] = [redact(frame)[:250] for frame in stack[:30]]
    return event


class DiagnosticLog(logging.Handler):
    """Never write to disk on the GUI thread; bound both queue and files."""
    def __init__(self, folder, version):
        super().__init__(logging.DEBUG)
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.version, self.session = version, str(uuid.uuid4())
        self.verbose_until = 0.0
        self.dropped = self.write_errors = 0
        self._queue = queue.Queue(maxsize=2000)
        self._stop = threading.Event()
        self._sink = RotatingFileHandler(self.folder / FILE_NAME, maxBytes=MAX_BYTES,
            backupCount=BACKUPS, encoding='utf-8', delay=True)
        self._sink.setFormatter(logging.Formatter('%(message)s'))
        self._writer = threading.Thread(target=self._write, name='Diagnostic writer', daemon=True)
        self._writer.start()

    def verbose_remaining(self):
        return max(0, int(self.verbose_until - time.monotonic()))

    def set_verbose(self, on):
        self.verbose_until = time.monotonic() + DEBUG_SECONDS if on else 0.0
        logging.getLogger('notepad.diagnostics').info('Detailed diagnostics enabled for 15 minutes' if on
            else 'Detailed diagnostics disabled', extra={'event': 'diagnostics.detail'})

    def emit(self, record):
        if self._stop.is_set() or not record.name.startswith(('notepad', 'core.', 'ui.', 'qt')):
            return
        if record.levelno < logging.INFO and not self.verbose_remaining():
            return
        try:
            self._queue.put_nowait(event_from_record(record, self.version, self.session))
        except queue.Full:
            self.dropped += 1
        except Exception:
            self.dropped += 1

    def _write(self):
        try:
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    event = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    line = json.dumps(event, ensure_ascii=False)
                    record = logging.LogRecord('diagnostic.file', logging.INFO, '', 0, line, (), None)
                    # Call the bounded sink directly: errors stay here, never recurse
                    # into the application's own logger or interfere with editing.
                    if self._sink.shouldRollover(record):
                        self._sink.doRollover()
                    if self._sink.stream is None:
                        self._sink.stream = self._sink._open()
                    self._sink.stream.write(line + '\n')
                    self._sink.flush()
                except (OSError, ValueError):
                    self.write_errors += 1
                finally:
                    self._queue.task_done()
        finally:
            self._sink.close()

    def flush_pending(self, timeout=1.0):
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)

    def close(self):
        self._stop.set()
        if self._writer is not threading.current_thread():
            self._writer.join(timeout=1)
        super().close()


def configure(version):
    global _runtime
    if _runtime is not None:
        logging.getLogger().removeHandler(_runtime)
        _runtime.close()
    _runtime = DiagnosticLog(settings_manager.app_data_dir() / 'logs', version)
    logging.getLogger().addHandler(_runtime)
    for name in ('notepad', 'core', 'ui', 'qt'):
        logging.getLogger(name).setLevel(logging.DEBUG)
    logging.getLogger('notepad.diagnostics').info('Application session started', extra={'event': 'session.start'})
    return _runtime


def runtime():
    return _runtime


def shutdown():
    global _runtime
    if _runtime is not None:
        logging.getLogger('notepad.diagnostics').info('Application session ended', extra={'event': 'session.end'})
        logging.getLogger().removeHandler(_runtime)
        _runtime.close()
        _runtime = None


def _safe_saved_event(raw):
    if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) for k in ('time', 'level', 'message')):
        return None
    allowed = ('time', 'level', 'message', 'component', 'event', 'id', 'session', 'version',
        'thread', 'source', 'operation', 'operation_id', 'request_id', 'route', 'method', 'reason', 'error_type')
    result = {key: redact(raw[key]) for key in allowed if isinstance(raw.get(key), str)}
    for key in ('duration_ms', 'http_status', 'os_error', 'tls_verify_code', 'uploaded', 'downloaded', 'deleted', 'conflicts', 'skipped', 'count'):
        if isinstance(raw.get(key), (float, int)) and not isinstance(raw[key], bool):
            result[key] = raw[key]
    if isinstance(raw.get('stack'), list):
        result['stack'] = [redact(row)[:250] for row in raw['stack'][:30] if isinstance(row, str)]
    if isinstance(raw.get('error_chain'), list):
        result['error_chain'] = [redact(row)[:100] for row in raw['error_chain'][:5] if isinstance(row, str)]
    return result


def read_events(folder=None, limit=VIEW_LIMIT):
    folder = Path(folder) if folder is not None else settings_manager.app_data_dir() / 'logs'
    events = []
    for suffix in ('', '.1', '.2'):
        path = folder / (FILE_NAME + suffix)
        try:
            with path.open('rb') as stream:
                size = stream.seek(0, 2)
                if size > MAX_BYTES + 32000:
                    stream.seek(size - MAX_BYTES - 32000)
                    stream.readline()
                else:
                    stream.seek(0)
                data = stream.read(MAX_BYTES + 32000).decode('utf-8', errors='replace')
        except FileNotFoundError:
            continue
        for line in reversed(data.splitlines()):
            try:
                event = _safe_saved_event(json.loads(line))
            except (ValueError, TypeError):
                continue
            if event:
                events.append(event)
                if len(events) >= limit:
                    return list(reversed(events))
    return list(reversed(events))


def crash_summary(folder):
    """Read only native crash headers/frames, never copy the raw crash file."""
    path = Path(folder) / 'crash.log'
    try:
        with path.open('rb') as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - 128000))
            text = stream.read(128000).decode('utf-8', errors='replace')
        stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
    except FileNotFoundError:
        return ''
    frames = []
    for filename, line, function in re.findall(r'File "([^"\r\n]+)", line (\d+)(?: in ([\w.<>]+))?', text):
        basename = re.split(r'[\\/]', filename)[-1]
        if re.fullmatch(r'[\w.\- ]+\.py', basename):
            frames.append(f'{basename}:{line} in {function}')
    if not frames:
        return ''
    return f'Historical native crash stack. File modified UTC: {stamp}\nMay belong to an earlier app version.\n' + '\n'.join(frames[-100:])


def environment_report(version):
    from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR

    service = runtime()
    report = {'app_version': version, 'system': platform.system(), 'os_release': platform.release(),
              'architecture_bits': 64 if sys.maxsize > 2**32 else 32, 'python': platform.python_version(),
              'qt': QT_VERSION_STR, 'pyqt': PYQT_VERSION_STR, 'packaged': bool(getattr(sys, 'frozen', False)),
              'session': service.session if service else None,
              'verbose_seconds_left': service.verbose_remaining() if service else 0,
              'dropped_events': service.dropped if service else 0,
              'log_write_errors': service.write_errors if service else 0}
    # Only presence/state flags. No keys, account identifiers, proxy, device
    # name, file names, document contents or configured filesystem paths.
    try:
        path = settings_manager.app_data_dir() / 'cloud_sync.json'
        raw = json.loads(path.read_text(encoding='utf-8-sig')) if path.stat().st_size < 32000 else {}
        if isinstance(raw, dict):
            report['sync_enabled'] = bool(raw.get('enabled'))
            report['sync_device_configured'] = bool(raw.get('device_id'))
    except (OSError, ValueError):
        pass
    return report


@traced('report.export')
def export_report(destination, version):
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('گزارش باید با پسوند zip ذخیره شود.')
    service = runtime()
    if service:
        service.flush_pending()
    events = read_events(limit=2000)
    native_stack = crash_summary(settings_manager.app_data_dir() / 'logs')
    fd, temporary = tempfile.mkstemp(prefix='.notepad-report-', suffix='.tmp', dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('environment.json', json.dumps(environment_report(version), ensure_ascii=False, indent=2))
            archive.writestr('events.jsonl', '\n'.join(json.dumps(event, ensure_ascii=False) for event in events))
            archive.writestr('README.txt', 'Notepad Plus diagnostic report. No notes, credentials or raw legacy logs included.\n')
            if native_stack:
                archive.writestr('crash-stack.txt', native_stack)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(events)
