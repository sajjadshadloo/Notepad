from core.external_change_monitor import ExternalChangeMonitor, file_stamp
from ui.main_window import MainWindow


def test_file_stamp_changes_with_file_contents(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("one", encoding="utf-8")
    before = file_stamp(path)

    path.write_text("longer text", encoding="utf-8")

    assert file_stamp(path) != before


def test_monitor_reports_external_change_once_until_acknowledged(tmp_path, qapp):
    path = tmp_path / "note.txt"
    path.write_text("one", encoding="utf-8")
    monitor = ExternalChangeMonitor()
    changes = []
    monitor.changed.connect(changes.append)
    monitor.watch(path)

    path.write_text("external update", encoding="utf-8")
    monitor._file_changed(str(path))
    monitor._file_changed(str(path))

    normalized = monitor._normalize(path)
    assert changes == [normalized]

    monitor.acknowledge(path)
    monitor._file_changed(str(path))
    assert changes == [normalized]


def test_monitor_reports_missing_file(tmp_path, qapp):
    path = tmp_path / "note.txt"
    path.write_text("text", encoding="utf-8")
    monitor = ExternalChangeMonitor()
    missing = []
    monitor.missing.connect(missing.append)
    monitor.watch(path)

    path.unlink()
    monitor._file_changed(str(path))

    assert missing == [monitor._normalize(path)]


def test_move_and_unwatch_update_monitored_paths(tmp_path, qapp):
    old_path = tmp_path / "old.txt"
    new_path = tmp_path / "new.txt"
    old_path.write_text("text", encoding="utf-8")
    monitor = ExternalChangeMonitor()
    monitor.watch(old_path)
    old_path.rename(new_path)

    monitor.move(old_path, new_path)

    assert monitor._normalize(old_path) not in monitor.watched_paths()
    assert monitor._normalize(new_path) in monitor.watched_paths()
    monitor.unwatch(new_path)
    assert not monitor.watched_paths()


def test_main_window_watches_and_reloads_open_document(tmp_path, qapp, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    path = tmp_path / "note.txt"
    path.write_text("original", encoding="utf-8")
    window = MainWindow([str(path)])
    window._recovery_timer.stop()
    normalized = window._file_monitor._normalize(path)

    assert normalized in window._file_monitor.watched_paths()

    path.write_text("changed elsewhere", encoding="utf-8")
    tab = window.current_document()
    assert window._reload_document_from_disk(tab)
    assert tab.text == "changed elsewhere"
    assert not tab.modified

    window._closing_application = True
    window.close_tab(0, create_replacement=False)
    assert normalized not in window._file_monitor.watched_paths()
    window.close()


def test_app_save_is_acknowledged_as_current_disk_version(tmp_path, qapp, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    path = tmp_path / "note.txt"
    path.write_text("original", encoding="utf-8")
    window = MainWindow([str(path)])
    window._recovery_timer.stop()
    external_changes = []
    window._file_monitor.changed.connect(external_changes.append)
    tab = window.current_document()
    tab.editor.setPlainText("saved by app")

    assert window._save_document(tab, str(path))
    window._file_monitor._file_changed(str(path))

    assert external_changes == []
    assert path.read_text(encoding="utf-8") == "saved by app"

    window._closing_application = True
    window.close_tab(0, create_replacement=False)
    window.close()
