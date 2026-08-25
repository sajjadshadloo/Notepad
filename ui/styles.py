DARK = {
    # Base pair requested for 2.5.0: #212128 (editor/window) + #2b2b33
    # (chrome surfaces). The alt/hover/border steps are derived from them.
    "window": "#212128",
    "surface": "#2b2b33",
    "surface_alt": "#33333d",
    "hover": "#3a3a45",
    "border": "#42424e",
    "text": "#e7e8ec",
    "muted": "#989aa6",
    "accent": "#4cc2ff",
    "accent_hover": "#73d1ff",
    "on_accent": "#10131a",
    "danger": "#ff6b78",
}

LIGHT = {
    "window": "#f9fafc",
    "surface": "#ffffff",
    "surface_alt": "#eef1f6",
    "hover": "#e6eaf1",
    "border": "#d9dde6",
    "text": "#1f2329",
    "muted": "#71798a",
    "accent": "#0067c0",
    "accent_hover": "#005aa8",
    "on_accent": "#ffffff",
    "danger": "#d84254",
}


def resolve_theme(theme: str) -> str:
    """Map a stored preference to a concrete 'dark'/'light' palette.

    'system' follows the OS color scheme (Windows/macOS/Linux via Qt).
    """
    if theme == "system":
        try:
            from PyQt6.QtGui import QGuiApplication
            from PyQt6.QtCore import Qt

            scheme = QGuiApplication.styleHints().colorScheme()
            return "light" if scheme == Qt.ColorScheme.Light else "dark"
        except Exception:
            return "dark"
    return "light" if theme == "light" else "dark"


# The palette the app is currently styled with. Widgets must read the
# theme from here, not from their QPalette: stylesheets never update the
# palette, so palette-based guesses go stale (light token colors were
# painted on the dark theme that way).
_current: dict = DARK


def current_palette() -> dict:
    return _current


def current_is_light() -> bool:
    return _current is LIGHT


def build_stylesheet(theme: str = "dark") -> str:
    global _current
    t = LIGHT if resolve_theme(theme) == "light" else DARK
    _current = t
    return f"""
/* No font-family here: a stylesheet font would override the per-editor
   QFont (and its Persian fallback chain). The app font is set in main.py. */
* {{
    outline: none;
}}

QMainWindow, QDialog, QMessageBox {{
    background: {t['window']};
    color: {t['text']};
}}

QMenuBar {{
    background: {t['surface']};
    color: {t['text']};
    border-bottom: 1px solid {t['border']};
    padding: 3px 8px;
}}
QMenuBar::item {{
    padding: 6px 11px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{ background: {t['hover']}; }}

QMenu {{
    background: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    padding: 5px;
}}
QMenu::item {{
    padding: 7px 24px;
    border-radius: 6px;
}}
QMenu::item:selected {{ background: {t['hover']}; color: {t['accent']}; }}
QMenu::separator {{
    height: 1px;
    background: {t['border']};
    margin: 5px 10px;
}}

#formatBar {{
    background: {t['surface']};
    border: none;
    border-bottom: 1px solid {t['border']};
    spacing: 2px;
    padding: 3px 10px;
}}
#formatBar QToolButton {{
    font-weight: 600;
    padding: 4px 9px;
}}
QToolButton {{
    background: transparent;
    color: {t['muted']};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 10px;
}}
QToolButton:hover {{
    background: {t['hover']};
    color: {t['text']};
}}
QToolButton:checked {{
    background: {t['surface_alt']};
    border-color: {t['accent']};
    color: {t['accent']};
}}
QToolBar::separator {{
    background: {t['border']};
    width: 1px;
    margin: 5px 7px;
}}

#documentTabs::pane {{
    border: none;
    background: {t['window']};
}}
QTabBar {{
    background: {t['surface']};
}}
QTabBar::tab {{
    background: {t['surface']};
    color: {t['muted']};
    border-right: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']};
    min-width: 120px;
    max-width: 240px;
    padding: 9px 14px;
}}
QTabBar::tab:hover {{ background: {t['hover']}; color: {t['text']}; }}
QTabBar::tab:selected {{
    background: {t['window']};
    color: {t['text']};
    border-bottom: 2px solid {t['accent']};
}}
QTabBar::close-button {{
    subcontrol-position: right;
}}
#newTabButton {{
    color: {t['text']};
    font-size: 18px;
    font-weight: 400;
    border-radius: 6px;
    padding: 0;
}}
#newTabButton:hover {{
    background: {t['hover']};
    color: {t['accent']};
}}

QTextEdit {{
    background: {t['window']};
    color: {t['text']};
    border: none;
    padding: 22px 26px;
    selection-background-color: {t['accent']};
    selection-color: {t['on_accent']};
}}
#lineNumberArea {{
    background: {t['window']};
    border: none;
}}
QStatusBar {{
    background: {t['surface']};
    color: {t['muted']};
    border-top: 1px solid {t['border']};
    min-height: 25px;
}}
#statusLabel {{
    color: {t['muted']};
    border-left: 1px solid {t['border']};
    padding: 0 10px;
}}
#statusButton {{
    background: transparent;
    color: {t['muted']};
    border: none;
    border-left: 1px solid {t['border']};
    border-radius: 0;
    padding: 2px 10px;
}}
#statusButton:hover {{
    color: {t['accent']};
    background: {t['hover']};
}}

QLineEdit {{
    background: {t['surface_alt']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 7px 10px;
}}
QLineEdit:focus {{ border-color: {t['accent']}; }}
QLabel, QCheckBox {{ color: {t['text']}; }}

QComboBox, QSpinBox {{
    background: {t['surface_alt']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 120px;
}}
QComboBox:focus, QSpinBox:focus {{ border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    selection-background-color: {t['hover']};
    selection-color: {t['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}

QGroupBox {{
    color: {t['muted']};
    font-weight: 600;
    border: 1px solid {t['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 10px 6px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

QPushButton {{
    background: {t['surface_alt']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {t['accent']}; color: {t['accent']}; }}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
}}
QScrollBar::handle:horizontal {{
    background: {t['border']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

#sidebar {{
    background: {t['surface']};
    border-right: 1px solid {t['border']};
}}
#sidebarHeader {{
    color: {t['muted']};
    font-weight: 600;
}}
#sidebarSearch {{
    background: {t['surface_alt']};
}}
#quickOpenList, #noteList {{
    background: transparent;
    border: none;
}}
#quickOpenList::item, #noteList::item {{
    padding: 8px 10px;
    border-radius: 6px;
    color: {t['text']};
}}
#quickOpenList::item:hover, #noteList::item:hover {{ background: {t['hover']}; }}
#quickOpenList::item:selected, #noteList::item:selected {{
    background: {t['hover']};
    color: {t['accent']};
}}
"""
