from datetime import datetime, timedelta

import pytest

from PyQt6.QtCore import Qt

from ui.sidebar import Sidebar


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    """MainWindow backed by a throwaway settings dir, never the real one."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow()
    window._cfg["notes_root"] = str(tmp_path / "notes")
    yield window
    window.close()


def _splitter_order(window) -> list[str]:
    return [
        window._splitter.widget(index).objectName()
        for index in range(window._splitter.count())
    ]


def test_sidebar_defaults_to_the_left(main_window):
    assert _splitter_order(main_window) == ["sidebar", "documentTabs"]


def test_sidebar_moves_to_the_right_and_back(main_window):
    """RTL users can park the sidebar on the right; the choice persists."""
    main_window.sidebar_right_action.trigger()
    assert _splitter_order(main_window) == ["documentTabs", "sidebar"]
    assert main_window._cfg["sidebar_on_right"] is True

    main_window.sidebar_right_action.trigger()
    assert _splitter_order(main_window) == ["sidebar", "documentTabs"]
    assert main_window._cfg["sidebar_on_right"] is False


def test_editor_pane_stays_uncollapsible_on_either_side(main_window):
    for _ in range(2):
        main_window.sidebar_right_action.trigger()
        editor_index = main_window._splitter.indexOf(main_window.tabs)
        assert not main_window._splitter.isCollapsible(editor_index)


def test_format_date_uses_last_opened_today(tmp_path, qapp):
    note = tmp_path / "note.md"
    note.write_text("hi", encoding="utf-8")
    entry = {"last_opened": datetime.now().isoformat()}

    label = Sidebar._format_date(str(note), entry)

    assert label == "Today"


def test_format_date_uses_yesterday(tmp_path, qapp):
    note = tmp_path / "note.md"
    note.write_text("hi", encoding="utf-8")
    yesterday = datetime.now() - timedelta(days=1)
    entry = {"last_opened": yesterday.isoformat()}

    label = Sidebar._format_date(str(note), entry)

    assert label == "Yesterday"


def test_format_date_falls_back_to_mtime(tmp_path, qapp):
    note = tmp_path / "note.md"
    note.write_text("hi", encoding="utf-8")

    label = Sidebar._format_date(str(note), {})

    assert label == "Today"


def test_persian_note_uses_vazirmatn_fallback_and_right_alignment(tmp_path, qapp):
    note = tmp_path / "یادداشت فارسی.txt"
    note.write_text("متن", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))

    item = sidebar.note_list.item(0)

    assert item.text().startswith(note.name)
    assert item.textAlignment() & int(Qt.AlignmentFlag.AlignRight)
    assert item.font().families()[:3] == ["Inter", "Vazirmatn", "Segoe UI"]
