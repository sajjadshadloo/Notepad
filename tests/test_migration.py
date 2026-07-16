import json

import core.migration as migration


def test_migration_creates_category_and_trash_folders(tmp_path, monkeypatch, qapp):
    source = tmp_path / "notes.json"
    source.write_text(
        json.dumps(
            {
                "notes": [
                    {
                        "title": "نمونه",
                        "category": "کار",
                        "content": "<p><b>سلام</b></p>",
                        "deleted": False,
                    },
                    {
                        "title": "نمونه",
                        "category": "کار",
                        "content": "متن ساده",
                        "deleted": True,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(migration, "legacy_notes_path", lambda: source)
    destination = tmp_path / "export"

    created = migration.migrate_legacy_notes(destination)

    assert len(created) == 2
    assert (destination / "کار" / "نمونه.md").exists()
    assert (destination / "حذف‌شده‌ها" / "نمونه.md").exists()
    assert "سلام" in (destination / "کار" / "نمونه.md").read_text(encoding="utf-8")


def test_migration_uses_unique_names(tmp_path, monkeypatch, qapp):
    source = tmp_path / "notes.json"
    source.write_text(
        json.dumps(
            {
                "notes": [
                    {"title": "A", "category": "General", "content": "1"},
                    {"title": "A", "category": "General", "content": "2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(migration, "legacy_notes_path", lambda: source)

    migration.migrate_legacy_notes(tmp_path / "out")

    assert (tmp_path / "out" / "General" / "A.md").exists()
    assert (tmp_path / "out" / "General" / "A (2).md").exists()
