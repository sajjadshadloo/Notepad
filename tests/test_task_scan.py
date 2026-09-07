"""The one folder walk every task surface shares.

This was `ui.reminder_service.scan_folder` until 4.0 removed reminders; the
walk itself is what the sidebar, Ctrl+T and Ctrl+P all still need.
"""
from core.task_scan import scan_folder


def test_it_finds_tasks_across_nested_notes(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.md").write_text("- [ ] یک @1405/06/05\n", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("- [x] دو\n", encoding="utf-8")

    found = {task.text for task in scan_folder(str(tmp_path))}
    assert found == {"یک", "دو"}


def test_it_ignores_files_that_are_not_notes(tmp_path):
    (tmp_path / "notes.md").write_text("- [ ] شمرده شود\n", encoding="utf-8")
    (tmp_path / "data.json").write_text("- [ ] نادیده\n", encoding="utf-8")

    assert [task.text for task in scan_folder(str(tmp_path))] == ["شمرده شود"]


def test_it_records_where_each_task_came_from(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("سطر اول\n- [ ] کار\n", encoding="utf-8")

    task = scan_folder(str(tmp_path))[0]
    assert task.path == str(path.resolve())
    assert task.line_number == 1


def test_a_missing_folder_is_not_an_error(tmp_path):
    assert scan_folder(str(tmp_path / "nowhere")) == []


def test_an_unreadable_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    (tmp_path / "good.md").write_text("- [ ] خوب\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("- [ ] بد\n", encoding="utf-8")

    import core.task_scan as module

    real = module.read_text_file

    def explode(path):
        if path.name == "bad.md":
            raise OSError("locked")
        return real(path)

    monkeypatch.setattr(module, "read_text_file", explode)
    assert [task.text for task in scan_folder(str(tmp_path))] == ["خوب"]
