"""The scheduler talks to Windows through schtasks, so these tests exercise
the parts that are ours: the XML we hand it, and the id scheme that decides
which reminders get created and which get removed.
"""
import xml.etree.ElementTree as ET
from datetime import datetime

import core.win_scheduler as win_scheduler

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
BACKSLASH = "\\"


def _parse(xml: str):
    return ET.fromstring(xml)


def test_start_time_is_iso_not_locale_formatted():
    """The whole reason for using XML: the /SD flag reads 04/09 as April or
    September depending on the machine's locale."""
    xml = win_scheduler.build_xml("x", datetime(2026, 9, 4, 7, 5), "--remind a")
    assert _parse(xml).find(".//t:StartBoundary", NS).text == "2026-09-04T07:05:00"


def test_task_text_is_escaped_into_the_xml():
    xml = win_scheduler.build_xml(
        "a <b> & 'c'", datetime(2026, 9, 4, 10, 0), "--remind a"
    )
    assert _parse(xml).find(".//t:Description", NS).text == "a <b> & 'c'"


def test_persian_text_survives():
    xml = win_scheduler.build_xml(
        "تحویل سایت بامسما", datetime(2026, 9, 4, 10, 0), "--remind a"
    )
    assert _parse(xml).find(".//t:Description", NS).text == "تحویل سایت بامسما"


def test_arguments_carry_the_identifier():
    xml = win_scheduler.build_xml(
        "x", datetime(2026, 9, 4, 10, 0), '--remind "abc123"'
    )
    assert _parse(xml).find(".//t:Arguments", NS).text == '--remind "abc123"'


def test_task_ids_are_stable_and_distinct():
    """A stable id is what lets a later scan recognise an already-scheduled
    reminder instead of registering it a second time."""
    key = "C:/notes/a.md::تحویل سایت"
    assert win_scheduler.task_id(key) == win_scheduler.task_id(key)
    assert win_scheduler.task_id(key) != win_scheduler.task_id(key + " ")
    assert len(win_scheduler.task_id(key)) == 16
    assert win_scheduler.task_id(key).isalnum()


def test_everything_lives_under_one_folder():
    assert win_scheduler._task_name("abc") == "NotepadPlus" + BACKSLASH + "abc"


def test_nothing_is_attempted_when_unavailable(tmp_path, monkeypatch):
    """From source the command would be `python main.py`, which cannot be
    relied on to still work when the task fires weeks later."""
    monkeypatch.setattr(win_scheduler, "available", lambda: False)
    called = []
    monkeypatch.setattr(win_scheduler, "_run", lambda args: called.append(args))

    assert not win_scheduler.register("k", "d", datetime(2026, 9, 4, 10, 0), tmp_path)
    assert not win_scheduler.unregister("abc")
    assert win_scheduler.registered_ids() == set()
    win_scheduler.clear_all()
    assert called == []


def test_registered_ids_reads_only_our_own_tasks(monkeypatch):
    monkeypatch.setattr(win_scheduler, "available", lambda: True)
    listing = (
        '"' + BACKSLASH + "NotepadPlus" + BACKSLASH + 'aaaa1111","9/4/2026","Ready"\n'
        '"' + BACKSLASH + "OtherApp" + BACKSLASH + 'bbbb2222","9/4/2026","Ready"\n'
        '"' + BACKSLASH + "Microsoft" + BACKSLASH + 'Defrag","N/A","Ready"\n'
    )

    class Result:
        returncode = 0
        stdout = listing

    monkeypatch.setattr(win_scheduler, "_run", lambda args: Result())
    assert win_scheduler.registered_ids() == {"aaaa1111"}


def test_a_schtasks_failure_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(win_scheduler, "available", lambda: True)

    class Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(win_scheduler, "_run", lambda args: Result())
    assert (
        win_scheduler.register("k", "d", datetime(2026, 9, 4, 10, 0), tmp_path) is False
    )
    assert win_scheduler.registered_ids() == set()


def test_the_definition_file_is_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(win_scheduler, "available", lambda: True)

    class Result:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(win_scheduler, "_run", lambda args: Result())
    win_scheduler.register("k", "d", datetime(2026, 9, 4, 10, 0), tmp_path)
    assert list(tmp_path.glob("*.xml")) == []


def test_the_definition_is_utf16_because_schtasks_demands_it(tmp_path, monkeypatch):
    monkeypatch.setattr(win_scheduler, "available", lambda: True)
    written = {}

    def fake_run(arguments):
        path = arguments[arguments.index("/XML") + 1]
        written["bytes"] = open(path, "rb").read()

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(win_scheduler, "_run", fake_run)
    win_scheduler.register("k", "کار", datetime(2026, 9, 4, 10, 0), tmp_path)
    assert written["bytes"][:2] in (b"\xff\xfe", b"\xfe\xff")  # a BOM
