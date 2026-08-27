from datetime import datetime, timedelta

import pytest

from PyQt6.QtCore import Qt

from ui.note_rows import ROLE_FIELDS
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
    assert _splitter_order(main_window) == ["sidebar", "documentPages"]


def test_sidebar_moves_to_the_right_and_back(main_window):
    """RTL users can park the sidebar on the right; the choice persists."""
    main_window.sidebar_right_action.trigger()
    assert _splitter_order(main_window) == ["documentPages", "sidebar"]
    assert main_window._cfg["sidebar_on_right"] is True

    main_window.sidebar_right_action.trigger()
    assert _splitter_order(main_window) == ["sidebar", "documentPages"]
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


def test_persian_note_reads_right_to_left(tmp_path, qapp):
    """Each row picks its direction from its own name, so a Persian note and
    snippets.txt can sit in the same list and both read correctly."""
    note = tmp_path / "یادداشت فارسی.txt"
    note.write_text("متن", encoding="utf-8")
    (tmp_path / "snippets.txt").write_text("x", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    directions = {}
    for row in range(sidebar.note_list.count()):
        fields = sidebar.note_list.item(row).data(ROLE_FIELDS) or {}
        if fields.get("title"):
            directions[fields["title"]] = fields["rtl"]

    assert directions["یادداشت فارسی.txt"] is True
    assert directions["snippets.txt"] is False


def test_the_note_font_carries_the_persian_fallback(tmp_path, qapp):
    """Segoe UI has Arabic glyphs, so the Persian family has to come first
    in the chain or Persian names quietly render in the wrong face."""
    (tmp_path / "یادداشت فارسی.txt").write_text("متن", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    assert sidebar.note_list.font().families()[:3] == [
        "Inter",
        "Vazirmatn",
        "Segoe UI",
    ]


def test_hidden_sidebar_defers_scanning_until_shown(tmp_path, qapp):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))

    assert sidebar.note_list.count() == 0  # hidden: no scan yet
    sidebar.refresh()
    assert sidebar.note_list.count() == 0  # still hidden: refresh only marks dirty

    sidebar.show()
    # showEvent runs the pending refresh: one heading and one note.
    assert sidebar.note_list.titles() == ["note.txt"]


def test_sidebar_shares_the_window_index_object(tmp_path, qapp):
    shared: dict = {}
    sidebar = Sidebar(str(tmp_path), shared)
    assert sidebar._index is shared


def test_subfolders_become_their_own_headings(tmp_path, qapp):
    """Notes used to be flattened by rglob, so a folder you organised into
    was invisible in the sidebar. Folders are the categorisation now."""
    (tmp_path / "loose.txt").write_text("a", encoding="utf-8")
    (tmp_path / "کارها").mkdir()
    (tmp_path / "کارها" / "امروز.txt").write_text("b", encoding="utf-8")
    (tmp_path / "کارها" / "فردا.md").write_text("c", encoding="utf-8")

    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    assert sidebar.note_list.headers() == ["کارها", "Root"]
    assert set(sidebar.note_list.titles()) == {
        "loose.txt",
        "امروز.txt",
        "فردا.md",
    }


def test_a_heading_row_cannot_be_opened(tmp_path, qapp):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("a", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    opened = []
    sidebar.note_activated.connect(opened.append)
    heading = sidebar.note_list.item(0)
    assert sidebar.note_list.path_of(heading) is None
    sidebar._activate_item(heading)
    assert opened == []


def test_the_open_note_is_marked_active(tmp_path, qapp):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    target = str((tmp_path / "b.txt").resolve())
    sidebar.set_active_note(target)

    active = [
        (sidebar.note_list.item(row).data(ROLE_FIELDS) or {}).get("title")
        for row in range(sidebar.note_list.count())
        if (sidebar.note_list.item(row).data(ROLE_FIELDS) or {}).get("active")
    ]
    assert active == ["b.txt"]


def test_grouping_survives_a_root_written_in_another_path_form(tmp_path, qapp):
    """The stored notes_root uses forward slashes while the scan resolves to
    backslashes; without resolving both, relative_to() fails on every file
    and the tree silently collapses back to a flat list."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "note.txt").write_text("a", encoding="utf-8")

    sidebar = Sidebar(str(tmp_path).replace("\\", "/"))
    sidebar.show()

    assert sidebar.note_list.headers() == ["sub"]
    assert sidebar.note_list.titles() == ["note.txt"]
