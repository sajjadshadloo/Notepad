"""Links between notes: parsing, resolving by name or path, and backlinks."""
from core.links import NoteIndex, backlinks, links_in


def _notes(tmp_path, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return NoteIndex(tmp_path)


def test_links_are_found_with_their_span():
    text = "میزبانی روی همان سرور [[اطلاعات هاست]] است\n- [ ] [[a|برچسب]]"
    found = links_in(text)
    assert [(l.target, l.label, l.line) for l in found] == [
        ("اطلاعات هاست", "اطلاعات هاست", 0), ("a", "برچسب", 1)]
    first = found[0]
    assert text.splitlines()[0][first.start:first.end] == "[[اطلاعات هاست]]"


def test_empty_or_broken_brackets_are_not_links():
    assert links_in("[[]] and [[ ]] and [single] and [[open") == []


def test_resolve_by_name_ignoring_case_and_extension(tmp_path):
    index = _notes(tmp_path, {"Projects/Selta.md": "# سلتا", "اطلاعات هاست.md": "x"})
    assert index.resolve("selta").name == "Selta.md"
    assert index.resolve("اطلاعات هاست").name == "اطلاعات هاست.md"
    assert index.resolve("Projects/selta.md").name == "Selta.md"
    assert index.resolve("missing") is None


def test_a_path_link_picks_the_right_one_of_two_names(tmp_path):
    index = _notes(tmp_path, {"a/note.md": "A", "b/note.md": "B"})
    assert index.resolve("b/note").parent.name == "b"


def test_backlinks_carry_the_surrounding_words(tmp_path):
    index = _notes(tmp_path, {
        "store.md": "# فروشگاه مروارید",
        "plan.md": "# برنامه توسعه‌ها\nبعد از تحویل [[store]] سراغ نسخه‌ی ۴.۳ برو.",
        "other.md": "بدون پیوند",
    })
    found = backlinks(index, tmp_path / "store.md")
    assert len(found) == 1
    link = found[0]
    assert link.title == "برنامه توسعه‌ها"
    assert (link.before, link.link, link.after) == ("بعد از تحویل", "store", " سراغ نسخه‌ی ۴.۳ برو.")


def test_a_note_never_backlinks_itself(tmp_path):
    index = _notes(tmp_path, {"self.md": "[[self]]"})
    assert backlinks(index, tmp_path / "self.md") == []


def test_titles_for_completion(tmp_path):
    index = _notes(tmp_path, {"a.md": "", "x/b.txt": "", "y/a.md": ""})
    assert sorted(index.titles()) == ["a", "b"]
