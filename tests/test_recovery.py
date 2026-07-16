from core import recovery_manager


def test_recovery_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))

    recovery_manager.save_recovery(
        "test-id",
        text="متن ذخیره‌نشده",
        path=None,
        encoding="utf-8",
        title="بدون عنوان",
        direction_mode="auto",
    )

    recovered = recovery_manager.load_recoveries()
    assert recovered == [
        {
            "id": "test-id",
            "text": "متن ذخیره‌نشده",
            "path": None,
            "encoding": "utf-8",
            "title": "بدون عنوان",
            "direction_mode": "auto",
        }
    ]

    recovery_manager.remove_recovery("test-id")
    assert recovery_manager.load_recoveries() == []
