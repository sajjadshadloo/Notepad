from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from ui.styles import DARK, LIGHT, resolve_theme

SECTIONS = [
    (
        "File",
        [
            ("Ctrl+N", "New document"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+S", "Save"),
            ("Ctrl+Shift+S", "Save as"),
            ("F2", "Rename document / file"),
            ("Ctrl+W", "Close tab"),
            ("Ctrl+Shift+T", "Reopen closed tab"),
            ("Ctrl+,", "Settings"),
        ],
    ),
    (
        "Editing",
        [
            ("Ctrl+Z / Ctrl+Y", "Undo / Redo"),
            ("Ctrl+X / C / V", "Cut / Copy / Paste"),
            ("Ctrl+A", "Select all"),
            ("F5", "Insert time and date"),
        ],
    ),
    (
        "Search",
        [
            ("Ctrl+F", "Find"),
            ("F3 / Shift+F3", "Find next / previous"),
            ("Ctrl+H", "Replace"),
            ("Ctrl+G", "Go to line"),
        ],
    ),
    (
        "Formatting",
        [
            ("Ctrl+B", "Bold"),
            ("Ctrl+1 / 2 / 3", "Heading 1 / 2 / 3"),
            ("Ctrl+Shift+7", "Numbered list"),
            ("Ctrl+Shift+8", "Bullet list"),
            ("Ctrl+Shift+9", "To-do list"),
            ("Ctrl+D", "Toggle to-do done"),
            ("Ctrl+Right Shift", "Right-to-left paragraph"),
            ("Ctrl+Left Shift", "Left-to-right paragraph"),
        ],
    ),
    (
        "View",
        [
            ("Ctrl+= / Ctrl+-", "Zoom in / out"),
            ("Ctrl+0", "Restore default zoom"),
            ("Ctrl+Mouse Wheel", "Zoom"),
            ("Ctrl+Shift+B", "Toggle sidebar"),
            ("Ctrl+Shift+M", "Markdown preview"),
        ],
    ),
]


class ShortcutsDialog(QDialog):
    def __init__(self, theme: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(460, 520)
        colors = LIGHT if resolve_theme(theme) == "light" else DARK

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setFrameShape(QTextBrowser.Shape.NoFrame)
        browser.setHtml(self._html(colors))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(browser)

    @staticmethod
    def _html(c: dict) -> str:
        parts = [
            f"<body style='color:{c['text']}; font-size:13px;'>"
        ]
        for title, rows in SECTIONS:
            parts.append(
                f"<p style='color:{c['accent']}; font-size:14px;'>"
                f"<b>{title}</b></p>"
                "<table cellspacing='0' cellpadding='5' width='100%'>"
            )
            for keys, description in rows:
                parts.append(
                    "<tr>"
                    f"<td width='42%' style='color:{c['accent']}; "
                    f"font-family:Consolas,monospace;'>{keys}</td>"
                    f"<td style='color:{c['text']};'>{description}</td>"
                    "</tr>"
                )
            parts.append("</table>")
        parts.append("</body>")
        return "".join(parts)
