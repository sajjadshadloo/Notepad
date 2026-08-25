from core.export_service import export_to_html, export_to_pdf


def test_export_to_html_renders_markdown(tmp_path, qapp):
    path = tmp_path / "note.html"
    export_to_html("# Title\n\nSome **bold** text.", str(path))

    content = path.read_text(encoding="utf-8")
    assert "Title" in content
    assert "bold" in content


def test_export_to_pdf_creates_file(tmp_path, qapp):
    path = tmp_path / "note.pdf"
    export_to_pdf("# Title\n\nمتن فارسی and English text.", str(path))

    assert path.exists()
    assert path.stat().st_size > 0
    # A real PDF, not just a file that happens to exist: the build strips
    # Qt6Pdf.dll, so this is what proves QPdfWriter still does the work.
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    assert b"%%EOF" in data[-1024:]
