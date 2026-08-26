from datetime import datetime, timedelta

import core.reminder_store as reminder_store
from core.jalali import format_date
from core.tasks import due_within, parse_document
from ui.reminder_service import scan_folder
from ui.today_view import group_of


def _write(folder, name, text):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_walks_subfolders_and_skips_other_files(tmp_path):
    _write(tmp_path, "a.md", "- [ ] یک @1405/06/05")
    _write(tmp_path, "sub/b.txt", "- [ ] دو @1405/06/06 10:00")
    _write(tmp_path, "c.png", "not text")

    tasks = scan_folder(str(tmp_path))
    assert sorted(t.text for t in tasks) == ["دو", "یک"]


def test_scan_survives_an_unreadable_file(tmp_path):
    """One bad file must not stop the reminder for everything else."""
    _write(tmp_path, "good.md", "- [ ] کار @1405/06/05")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00broken")

    assert [t.text for t in scan_folder(str(tmp_path))] == ["کار"]


def test_only_tasks_that_are_due_fire(tmp_path):
    now = datetime(2026, 8, 25, 12, 0)
    soon = format_date(now.date(), persian_digits=False)
    later = format_date((now + timedelta(days=30)).date(), persian_digits=False)
    tasks = parse_document(
        f"- [ ] حالا @{soon} 09:00\n"
        f"- [ ] بعد @{later} 09:00\n"
        f"- [x] انجام‌شده @{soon} 09:00"
    )
    assert [t.text for t in due_within(tasks, now)] == ["حالا"]


def test_notified_state_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    assert reminder_store.load() == set()

    reminder_store.save({"C:/n/a.md::کار"})
    assert reminder_store.load() == {"C:/n/a.md::کار"}


def test_notified_state_is_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    reminder_store.save({f"k{i}" for i in range(reminder_store.MAX_ENTRIES + 250)})
    assert len(reminder_store.load()) == reminder_store.MAX_ENTRIES


def test_a_task_key_changes_when_its_text_or_file_does():
    """The key is what stops a reminder repeating — and what lets an edited
    task legitimately fire again."""
    a, b = parse_document("- [ ] کار @1405/06/05", "C:/n/a.md")[0], \
           parse_document("- [ ] کار @1405/06/05", "C:/n/b.md")[0]
    assert a.key() != b.key()
    changed = parse_document("- [ ] کار دیگر @1405/06/05", "C:/n/a.md")[0]
    assert changed.key() != a.key()


def test_today_view_grouping():
    now = datetime(2026, 8, 25, 12, 0)
    tasks = parse_document(
        "- [ ] گذشته @1405/06/01 09:00\n"
        "- [ ] امروز @1405/06/03 18:00\n"
        "- [ ] فردا @1405/06/04 09:00\n"
        "- [ ] دور @1405/07/01 09:00\n"
        "- [ ] بی‌تاریخ"
    )
    assert [group_of(t, now) for t in tasks] == [
        "عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ",
    ]


class _FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, body, icon, timeout):
        self.messages.append((title, body))


def _service(tmp_path, monkeypatch):
    """A ReminderService with the tray and scheduler stubbed out."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    from PyQt6.QtGui import QIcon

    import ui.reminder_service as module

    monkeypatch.setattr(module.win_scheduler, "available", lambda: False)
    service = module.ReminderService(str(tmp_path), QIcon(), schedule=False)
    service._tray = _FakeTray()
    return service


def test_a_reminder_is_announced_once(tmp_path, monkeypatch, qapp):
    """The --remind launch used to announce without recording it, so the
    next scan a minute later said the same thing again."""
    from datetime import datetime, timedelta

    from core.tasks import parse_document
    from core.jalali import format_date

    service = _service(tmp_path, monkeypatch)
    past = format_date(datetime.now().date(), persian_digits=False)
    tasks = parse_document(f"- [ ] کار @{past} 00:01", "C:/n/a.md")

    service._handle_tasks(tasks)
    assert len(service._tray.messages) == 1

    # A second scan of the same still-unfinished task must stay quiet.
    service._handle_tasks(tasks)
    assert len(service._tray.messages) == 1


def test_remind_by_id_does_not_double_announce(tmp_path, monkeypatch, qapp):
    from datetime import datetime

    import core.win_scheduler as win_scheduler
    from core.jalali import format_date
    from core.tasks import parse_document

    service = _service(tmp_path, monkeypatch)
    today = format_date(datetime.now().date(), persian_digits=False)
    tasks = parse_document(f"- [ ] کار @{today} 00:01", "C:/n/a.md")
    identifier = win_scheduler.task_id(tasks[0].key())

    service._by_id = {identifier: tasks[0]}
    assert service.show_by_id(identifier)
    assert len(service._tray.messages) == 1

    # The scan that follows the launch must not repeat it.
    service._handle_tasks(tasks)
    assert len(service._tray.messages) == 1


def test_an_unknown_id_is_reported(tmp_path, monkeypatch, qapp):
    service = _service(tmp_path, monkeypatch)
    assert service.show_by_id("nosuchid") is False
