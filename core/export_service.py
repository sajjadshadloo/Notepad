from PyQt6.QtGui import QTextDocument
from PyQt6.QtPrintSupport import QPrinter

from core.file_service import write_text_file_atomic


def export_to_pdf(markdown_text: str, path: str):
    document = QTextDocument()
    document.setMarkdown(markdown_text)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    document.print(printer)


def export_to_html(markdown_text: str, path: str):
    document = QTextDocument()
    document.setMarkdown(markdown_text)
    write_text_file_atomic(path, document.toHtml(), "utf-8")
