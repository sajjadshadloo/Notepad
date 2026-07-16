import codecs

import pytest

from core.file_service import read_text_file, write_text_file_atomic


@pytest.mark.parametrize(
    ("encoding", "bom"),
    [
        ("utf-8", b""),
        ("utf-8-sig", codecs.BOM_UTF8),
        ("utf-16-le", codecs.BOM_UTF16_LE),
        ("utf-16-be", codecs.BOM_UTF16_BE),
    ],
)
def test_round_trip_preserves_encoding(tmp_path, encoding, bom):
    path = tmp_path / "note.txt"
    text = "سلام دنیا\nHello"

    write_text_file_atomic(path, text, encoding)
    loaded = read_text_file(path)

    assert path.read_bytes().startswith(bom)
    assert loaded.text == text
    assert loaded.encoding == encoding


def test_windows_1256_is_detected(tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes("سلام".encode("cp1256"))

    loaded = read_text_file(path)

    assert loaded.text == "سلام"
    assert loaded.encoding == "cp1256"


def test_failed_encoding_does_not_replace_existing_file(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("original", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        write_text_file_atomic(path, "سلام", "cp1252")

    assert path.read_text(encoding="utf-8") == "original"
