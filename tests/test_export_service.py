from docx import Document

from core.export_service import export_to_docx, export_to_html, export_to_pdf


def test_export_to_html_renders_markdown(tmp_path, qapp):
    path = tmp_path / "note.html"
    export_to_html("# Title\n\nSome **bold** text.", str(path))

    content = path.read_text(encoding="utf-8")
    assert "Title" in content
    assert "bold" in content


def test_export_to_pdf_creates_file(tmp_path, qapp):
    path = tmp_path / "note.pdf"
    export_to_pdf("# Title\n\nSome text.", str(path))

    assert path.exists()
    assert path.stat().st_size > 0


def test_export_to_docx_preserves_structure(tmp_path):
    markdown_text = (
        "# Heading One\n"
        "## Heading Two\n"
        "- bullet item\n"
        "1. numbered item\n"
        "Plain paragraph with **bold** and *italic*.\n"
    )
    path = tmp_path / "note.docx"
    export_to_docx(markdown_text, str(path))

    document = Document(str(path))
    paragraphs = document.paragraphs

    assert paragraphs[0].text == "Heading One"
    assert paragraphs[0].style.name.startswith("Heading")
    assert paragraphs[1].text == "Heading Two"
    assert paragraphs[2].text == "bullet item"
    assert paragraphs[2].style.name == "List Bullet"
    assert paragraphs[3].text == "numbered item"
    assert paragraphs[3].style.name == "List Number"

    last = paragraphs[4]
    assert "bold" in last.text
    assert "italic" in last.text
    bold_runs = [run for run in last.runs if run.bold]
    italic_runs = [run for run in last.runs if run.italic]
    assert any(run.text == "bold" for run in bold_runs)
    assert any(run.text == "italic" for run in italic_runs)
