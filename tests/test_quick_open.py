from core.quick_open import Candidate, rank, score
from ui.quick_open import collect_candidates


def _c(relative: str) -> Candidate:
    name = relative.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return Candidate(path="/notes/" + relative, relative=relative, name=name)


def test_exact_name_beats_a_longer_one_that_starts_the_same():
    items = [_c("sitemap.txt"), _c("site.txt"), _c("website-notes.md")]
    assert [c.relative for c in rank("site", items)] == [
        "site.txt",
        "sitemap.txt",
        "website-notes.md",
    ]


def test_folder_name_finds_the_notes_inside_it():
    """Folders are the categorisation, so typing one has to work."""
    items = [_c("work/monday.md"), _c("personal/diary.md")]
    assert [c.relative for c in rank("work", items)] == ["work/monday.md"]


def test_matching_is_case_insensitive_and_works_in_persian():
    items = [_c("کارهای امروز.txt"), _c("Meeting Notes.md")]
    assert [c.relative for c in rank("meeting", items)] == ["Meeting Notes.md"]
    assert [c.relative for c in rank("امروز", items)] == ["کارهای امروز.txt"]


def test_scattered_letters_still_match_as_a_last_resort():
    """A subsequence match is what lets a few letters stand in for a name."""
    assert score("mnt", _c("monday-notes.txt")) is not None
    assert score("zqx", _c("monday-notes.txt")) is None


def test_empty_query_lists_everything():
    items = [_c("a.txt"), _c("b.txt")]
    assert len(rank("", items)) == 2


def test_no_match_returns_nothing():
    assert rank("zzzz", [_c("a.txt")]) == []


def test_collect_candidates_walks_subfolders_and_skips_other_files(tmp_path):
    (tmp_path / "root.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.md").write_text("b", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")

    found = {c.relative for c in collect_candidates(str(tmp_path))}
    assert found == {"root.txt", "sub/deep.md"}


def test_collect_candidates_tolerates_a_missing_folder(tmp_path):
    assert collect_candidates(str(tmp_path / "nope")) == []
