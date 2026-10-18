"""Exercise the desktop against synthetic notes, never the user's profile."""
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
DATA = ROOT / '.smoke-data' / 'desktop-stability-4.4.2'
os.environ['NOTEPAD_DATA_DIR'] = str(DATA / 'profile')

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from core import settings_manager
from ui.main_window import MainWindow, _load_bundled_fonts
from ui.styles import build_stylesheet


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    if not predicate():
        raise RuntimeError('Timed out waiting for desktop data')


def main():
    notes = DATA / 'notes'
    notes.mkdir(parents=True, exist_ok=True)
    for number in range(1000):
        (notes / f'note-{number:04}.md').write_text(
            f'# یادداشت آزمایشی {number}\n\nمتن فارسی و English برای بررسی نمایش.\n'
            + '- [ ] یک کار آزمایشی\n' * 20, encoding='utf-8')
    app = QApplication([])
    app.setApplicationName('NotepadReleaseReview')
    _load_bundled_fonts()
    app.setStyleSheet(build_stylesheet('dark', 'graphite'))
    settings_manager.save({**settings_manager.DEFAULTS, 'notes_root': str(notes),
        'default_save_dir': str(notes), 'migration_checked': True, 'daily_cleanup_done': True,
        'review_date': date.today().isoformat(), 'close_to_tray': False})
    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
    gaps, previous = [], [time.monotonic()]

    def heartbeat():
        now = time.monotonic()
        gaps.append((now - previous[0]) * 1000)
        previous[0] = now

    timer = QTimer(interval=10)
    timer.timeout.connect(heartbeat)
    started = time.monotonic()
    timer.start()
    window = MainWindow()
    window.resize(1360, 820)
    window.show()
    QTest.qWait(20)
    interactive_ms = (time.monotonic() - started) * 1000
    wait_for(lambda: window.notes_board._loader is None and len(window.notes_board.cards()) == 1000)
    wait_for(lambda: window._tasks_watcher._worker is None)
    window.grab().save(str(DATA / 'dashboard.png'))
    window.show_page('editor')
    QTest.keyClicks(window.current_document().editor, 'Editing after loading 1000 notes')
    assert window.current_document().text == 'Editing after loading 1000 notes'
    wait_for(lambda: window._links_worker is None)
    window.settings_overlay.open_with(window._settings_state(), 'sync')
    QTest.qWait(50)
    window.grab().save(str(DATA / 'telegram-settings.png'))
    window.settings_overlay.close_overlay()
    window.show_review()
    QTest.qWait(50)
    window.grab().save(str(DATA / 'welcome.png'))
    window.review.close_overlay()
    timer.stop()
    report = {'platform': app.platformName(), 'platform_option': os.environ.get('QT_QPA_PLATFORM', ''),
              'notes': len(window.notes_board.cards()), 'first_interaction_ms': round(interactive_ms, 1),
              'max_event_loop_gap_ms': round(max(gaps), 1), 'heartbeats': len(gaps),
              'greeting': window.review._hello.text, 'editing': 'ok'}
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._really_quitting = True
    window.close()
    app.processEvents()
    (DATA / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
