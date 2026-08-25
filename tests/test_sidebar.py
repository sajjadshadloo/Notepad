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
    sidebar.show()

    item = sidebar.note_list.topLevelItem(0)

    assert item.text(0) == note.name
    assert item.textAlignment(0) & int(Qt.AlignmentFlag.AlignRight)
    assert item.font(0).families()[:3] == ["Inter", "Vazirmatn", "Segoe UI"]


def test_hidden_sidebar_defers_scanning_until_shown(tmp_path, qapp):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))

    assert sidebar.note_list.topLevelItemCount() == 0  # hidden: no scan yet
    sidebar.refresh()
    assert sidebar.note_list.topLevelItemCount() == 0  # still hidden: refresh only marks dirty

    sidebar.show()
    assert sidebar.note_list.topLevelItemCount() == 1  # showEvent runs the pending refresh


def test_sidebar_shares_the_window_index_object(tmp_path, qapp):
    shared: dict = {}
    sidebar = Sidebar(str(tmp_path), shared)
    assert sidebar._index is shared


def test_subfolders_become_collapsible_groups(tmp_path, qapp):
    """Notes used to be flattened by rglob, so a folder you organised into
    was invisible in the sidebar. Folders are the categorisation now."""
    (tmp_path / "loose.txt").write_text("a", encoding="utf-8")
    (tmp_path / "کارها").mkdir()
    (tmp_path / "کارها" / "امروز.txt").write_text("b", encoding="utf-8")
    (tmp_path / "کارها" / "فردا.md").write_text("c", encoding="utf-8")

    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    top = [
        sidebar.note_list.topLevelItem(i)
        for i in range(sidebar.note_list.topLevelItemCount())
    ]
    labels = [item.text(0) for item in top]
    assert "loose.txt" in labels

    folders = [item for item in top if item.childCount()]
    assert len(folders) == 1
    folder = folders[0]
    assert "کارها" in folder.text(0)
    assert folder.isExpanded()
    assert {folder.child(i).text(0) for i in range(folder.childCount())} == {
        "امروز.txt",
        "فردا.md",
    }
    # A folder row carries no path, so it can only expand, never "open".
    assert folder.data(0, Qt.ItemDataRole.UserRole) is None


def test_clicking_a_folder_toggles_it_without_opening_anything(tmp_path, qapp):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("a", encoding="utf-8")
    sidebar = Sidebar(str(tmp_path))
    sidebar.show()

    opened = []
    sidebar.note_activated.connect(opened.append)
    folder = sidebar.note_list.topLevelItem(0)
    was_expanded = folder.isExpanded()
    sidebar._activate_item(folder)

    assert opened == []
    assert folder.isExpanded() is not was_expanded


def test_grouping_survives_a_root_written_in_another_path_form(tmp_path, qapp):
    """The stored notes_root uses forward slashes while the scan resolves to
    backslashes; without resolving both, relative_to() fails on every file
    and the tree silently collapses back to a flat list."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "note.txt").write_text("a", encoding="utf-8")

    sidebar = Sidebar(str(tmp_path).replace("\\", "/"))
    sidebar.show()

    top = [
        sidebar.note_list.topLevelItem(i)
        for i in range(sidebar.note_list.topLevelItemCount())
    ]
    assert [item.childCount() for item in top] == [1], [i.text(0) for i in top]
