from PyQt6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from ui.styles import DEFAULT_PALETTE, palette_for

SECTIONS = [
    (
        "File",
        [
            ("Ctrl+N", "New document"),
            ("Ctrl+O", "Open file"),
            ("Ctrl+P / Ctrl+K", "Go to file, task or command"),
            ("Ctrl+Shift+W", "Show the day widget on the desktop"),
            ("Ctrl+T", "My tasks — everything with a date"),
            ("Ctrl+Shift+D", "Open the tasks file"),
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
            ("Ctrl+Shift+A", "Give the task under the cursor a date"),
            ("Ctrl+Right Shift", "Right-to-left paragraph"),
            ("Ctrl+Left Shift", "Left-to-right paragraph"),
        ],
    ),
    (
        "View",
        [
            ("Ctrl+E", "Reading view — the note as a finished page"),
            ("Ctrl+= / Ctrl+-", "Zoom in / out"),
            ("Ctrl+0", "Restore default zoom"),
            ("Ctrl+Mouse Wheel", "Zoom"),
        ],
    ),
]


class ShortcutsDialog(QDialog):
    def __init__(self, theme: str, parent=None, palette: str = DEFAULT_PALETTE):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(460, 520)
        colors = palette_for(theme, palette)

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
