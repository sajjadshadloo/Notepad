from core.search_service import search_notes


def test_search_finds_matches_across_files(tmp_path):
    (tmp_path / "note1.md").write_text(
        "first line\nProject deadline is Friday\n", encoding="utf-8"
    )
    (tmp_path / "note2.txt").write_text(
        "unrelated content\nanother line\n", encoding="utf-8"
    )

    results = search_notes(str(tmp_path), "deadline")

    assert len(results) == 1
    assert results[0].path.endswith("note1.md")
    assert results[0].line_number == 2
    assert "deadline" in results[0].snippet.lower()


def test_title_matches_come_first(tmp_path):
    (tmp_path / "shopping list.md").write_text("milk\n", encoding="utf-8")
    (tmp_path / "other.md").write_text(
        "remember the shopping bags\n", encoding="utf-8"
    )

    results = search_notes(str(tmp_path), "shopping")

    assert len(results) == 2
    assert results[0].path.endswith("shopping list.md")
    assert results[0].line_number == 0
    assert results[0].snippet == ""
    assert results[1].path.endswith("other.md")


def test_persian_title_match(tmp_path):
    (tmp_path / "سایت حمید.txt").write_text("محتوا\n", encoding="utf-8")

    results = search_notes(str(tmp_path), "حمید")

    assert len(results) == 1
    assert results[0].line_number == 0


def test_title_matched_file_is_listed_once(tmp_path):
    (tmp_path / "deadline.md").write_text(
        "deadline here\ndeadline there\n", encoding="utf-8"
    )

    results = search_notes(str(tmp_path), "deadline")

    assert len(results) == 1
    assert results[0].line_number == 0


def test_search_is_case_insensitive_by_default(tmp_path):
    (tmp_path / "note.md").write_text("Important Client Meeting\n", encoding="utf-8")

    results = search_notes(str(tmp_path), "client")

    assert len(results) == 1


def test_search_case_sensitive_flag(tmp_path):
    (tmp_path / "note.md").write_text("Important Client Meeting\n", encoding="utf-8")

    results = search_notes(str(tmp_path), "client", case_sensitive=True)

    assert results == []


def test_search_skips_unsupported_extensions(tmp_path):
    (tmp_path / "ignored.bin").write_bytes(b"\x00\x01deadline\x02")
    (tmp_path / "note.md").write_text("no match here\n", encoding="utf-8")

    results = search_notes(str(tmp_path), "deadline")

    assert results == []


def test_search_empty_query_returns_empty(tmp_path):
    (tmp_path / "note.md").write_text("some text\n", encoding="utf-8")

    assert search_notes(str(tmp_path), "") == []


def test_search_missing_root_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert search_notes(str(missing), "anything") == []
