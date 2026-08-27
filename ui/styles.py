"""Colour tokens and the application stylesheet.

Every colour in the app comes from one of eleven tokens. A palette is one
dark/light pair of those eleven; the theme picks which half is used. Nothing
outside this module names a hex value, so a new palette is a data change.
"""

PALETTES = {
    # The default. Neutral grey chrome, a cool blue accent.
    "graphite": {
        "label": "Graphite",
        "dark": {
            "window": "#191a1f",
            "surface": "#212328",
            "surface_alt": "#2a2c33",
            "hover": "#31343c",
            "border": "#3a3d47",
            "text": "#e8e9ec",
            "muted": "#969aa5",
            "accent": "#6cb6ff",
            "accent_hover": "#8ec8ff",
            "on_accent": "#0d1117",
            "danger": "#ff7a85",
        },
        "light": {
            "window": "#fbfbfd",
            "surface": "#ffffff",
            "surface_alt": "#f1f3f7",
            "hover": "#e8ebf1",
            "border": "#dde1e8",
            "text": "#1c1f25",
            "muted": "#6b7280",
            "accent": "#1a6fd4",
            "accent_hover": "#155ab0",
            "on_accent": "#ffffff",
            "danger": "#d0384a",
        },
    },
    # Warm paper-and-ink. Easier on the eyes over a long evening.
    "amber": {
        "label": "Ink & Amber",
        "dark": {
            "window": "#1a1917",
            "surface": "#221f1c",
            "surface_alt": "#2b2723",
            "hover": "#332e28",
            "border": "#3d372f",
            "text": "#ece7de",
            "muted": "#a09889",
            "accent": "#e9a86a",
            "accent_hover": "#f4bd88",
            "on_accent": "#1a1207",
            "danger": "#ef6f63",
        },
        "light": {
            "window": "#fcfbf8",
            "surface": "#ffffff",
            "surface_alt": "#f4f1ea",
            "hover": "#ece7dd",
            "border": "#e2dcd0",
            "text": "#22201b",
            "muted": "#736c60",
            "accent": "#b06f13",
            "accent_hover": "#8f5808",
            "on_accent": "#ffffff",
            "danger": "#c2452f",
        },
    },
    "violet": {
        "label": "Slate & Violet",
        "dark": {
            "window": "#17181d",
            "surface": "#1e2027",
            "surface_alt": "#272a33",
            "hover": "#2f323d",
            "border": "#383c48",
            "text": "#e6e8ee",
            "muted": "#9096a5",
            "accent": "#a698ff",
            "accent_hover": "#bcb0ff",
            "on_accent": "#12101f",
            "danger": "#ff7b93",
        },
        "light": {
            "window": "#fafaff",
            "surface": "#ffffff",
            "surface_alt": "#f1f2f9",
            "hover": "#e8e9f4",
            "border": "#dcdeeb",
            "text": "#1b1c24",
            "muted": "#6a6e80",
            "accent": "#5b4fd6",
            "accent_hover": "#4a3fc0",
            "on_accent": "#ffffff",
            "danger": "#d23a5c",
        },
    },
}

DEFAULT_PALETTE = "graphite"

# The eleven token names every palette half must define. Anything that reads
# a colour reads one of these.
TOKENS = tuple(PALETTES[DEFAULT_PALETTE]["dark"])

# Kept as names because the shortcuts sheet and older call sites ask for the
# two halves directly.
DARK = PALETTES[DEFAULT_PALETTE]["dark"]
LIGHT = PALETTES[DEFAULT_PALETTE]["light"]


def palette_names() -> list[str]:
    return list(PALETTES)


def palette_label(name: str) -> str:
    return PALETTES.get(name, PALETTES[DEFAULT_PALETTE])["label"]


def palette_for(theme: str, name: str = DEFAULT_PALETTE) -> dict:
    """The eleven tokens for one theme/palette pair.

    An unknown palette falls back to the default rather than raising: a
    settings file carried over from an older version names none of these.
    """
    chosen = PALETTES.get(name) or PALETTES[DEFAULT_PALETTE]
    return chosen["light" if resolve_theme(theme) == "light" else "dark"]


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
# Tracked separately: with three palettes there is no single LIGHT dict to
# compare identity against, and two palettes can share a token value.
_current_light: bool = False


def current_palette() -> dict:
    return _current


def current_is_light() -> bool:
    return _current_light


def build_stylesheet(theme: str = "dark", palette: str = DEFAULT_PALETTE) -> str:
    global _current, _current_light
    _current_light = resolve_theme(theme) == "light"
    t = palette_for(theme, palette)
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

/* The top bar — the design's own row, and what stands in for a menu bar. */
#topBar {{
    background: {t['surface']};
    border-bottom: 1px solid {t['border']};
}}
#topBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {t['muted']};
    padding: 0 6px;
    font-size: 12px;
}}
#topBar QToolButton:hover {{ background: {t['hover']}; color: {t['text']}; }}
#topBar QToolButton:checked {{
    background: {t['surface_alt']};
    color: {t['accent']};
}}
#tasksButton {{ padding: 0 9px; }}
#breadcrumb {{ color: {t['muted']}; font-size: 12px; }}
/* The search field sits on the window colour so it reads as a well in the
   chrome, and it is a button that looks like a field on purpose. */
#topSearch {{
    background: {t['window']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 0;
    text-align: left;
}}
#topSearch:hover {{ border-color: {t['accent_hover']}; }}
#topSearchLabel {{ color: {t['muted']}; font-size: 12px; }}
#topSearchHint {{
    color: {t['muted']};
    border: 1px solid {t['border']};
    border-radius: 5px;
    padding: 1px 6px;
    font-size: 10px;
}}

/* The format bar sits on the window colour, not the chrome colour, so it
   reads as the top edge of the page rather than a second grey band. */
#formatBar {{
    background: {t['window']};
    border: none;
    border-bottom: 1px solid {t['border']};
    spacing: 3px;
    padding: 4px 12px;
}}
/* Enough padding that the hover fill reads as a button rather than a sticker
   pressed onto the glyph. The design's button is 24px tall around an 11.5px
   label, which is most of the height as breathing room. */
#formatBar QToolButton {{
    font-weight: 600;
    font-size: 11px;
    padding: 6px 10px;
    min-width: 26px;
    border-radius: 6px;
}}
QToolButton {{
    background: transparent;
    color: {t['muted']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 9px;
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

/* Today's progress, shown at the right end of the tab strip. */
#todayMeter {{
    background: {t['surface_alt']};
    border: none;
    border-radius: 3px;
    max-height: 5px;
    min-height: 5px;
    text-align: center;
}}
#todayMeter::chunk {{
    background: {t['accent']};
    border-radius: 3px;
}}
#todayMeterLabel {{
    color: {t['text']};
    font-size: 11px;
}}
#todayMeterCaption {{
    color: {t['muted']};
    font-size: 11px;
}}

#documentTabs {{
    background: {t['surface']};
    border-bottom: 1px solid {t['border']};
}}
#documentPages {{ background: {t['window']}; }}
/* Tabs are separated pills on the chrome band, not a filing-cabinet row
   of joined rectangles: no dividing lines, a rounded body, and the active
   one lifted onto the window colour. */
QTabBar {{
    background: {t['surface']};
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    /* Room for the 6px status dot the window sets as the tab icon. */
    color: {t['muted']};
    border: 1px solid transparent;
    border-radius: 8px;
    min-width: 90px;
    max-width: 210px;
    padding: 5px 9px;
    margin: 5px 2px;
}}
QTabBar::tab:hover {{ background: {t['hover']}; color: {t['text']}; }}
QTabBar::tab:selected {{
    background: {t['window']};
    color: {t['text']};
    border-color: {t['border']};
}}
QTabBar::close-button {{
    subcontrol-position: right;
}}
#newTabButton {{
    color: {t['muted']};
    font-size: 16px;
    font-weight: 400;
    border-radius: 7px;
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
    min-height: 30px;
}}
QStatusBar::item {{ border: none; }}
/* No dividing rules between status items — the design separates them with
   space, and gives the two clickable ones a pill so they read as buttons. */
#statusLabel {{
    color: {t['muted']};
    font-size: 11px;
    border: none;
    padding: 0 6px;
}}
#savedLabel {{
    font-size: 11px;
    border: none;
    padding: 0 6px;
}}
#savedLabel[dirty="true"] {{ color: {t['danger']}; }}
#savedLabel[dirty="false"] {{ color: {t['muted']}; }}
#statusButton {{
    background: {t['surface_alt']};
    color: {t['muted']};
    border: 1px solid {t['border']};
    border-radius: 9px;
    font-size: 11px;
    padding: 2px 9px;
    margin: 0 2px;
}}
#statusButton:hover {{
    color: {t['accent']};
    border-color: {t['accent']};
    background: {t['surface_alt']};
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
/* Qt's stock indicator is not themed and came out pink against every
   palette. Drawn from the tokens like everything else. */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {t['border']};
    border-radius: 4px;
    background: {t['window']};
}}
QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
    image: none;
}}
QCheckBox::indicator:disabled {{ border-color: {t['border']}; }}

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
/* The search field sits on the window colour so it reads as a well cut
   into the sidebar rather than another raised surface. */
#sidebarSearch {{
    background: {t['window']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 5px 9px;
}}
#sidebarSearch:focus {{ border-color: {t['accent']}; }}

/* Notes / Tasks / Calendar — one segmented control, not three stacked
   panes fighting for the same column. */
#sidebarSwitch {{
    background: {t['surface_alt']};
    border-radius: 9px;
    padding: 3px;
}}
/* The three segments share the width equally (see Sidebar._build_switch),
   so the selected fill is a whole third — not a pill shrink-wrapped around
   whichever label happens to be longest. */
#sidebarSwitch QToolButton {{
    background: transparent;
    color: {t['muted']};
    border: none;
    border-radius: 7px;
    padding: 7px 6px;
    font-size: 11px;
}}
#sidebarSwitch QToolButton:hover {{ color: {t['text']}; }}
#sidebarSwitch QToolButton:checked {{
    background: {t['surface']};
    color: {t['text']};
    font-weight: 600;
}}
#sidebarSectionLabel {{
    color: {t['muted']};
    font-size: 10px;
    font-weight: 600;
    padding: 6px 8px 2px;
}}
#weekAheadRow {{ color: {t['text']}; font-size: 11px; }}
#weekAheadCount {{ color: {t['muted']}; font-size: 11px; }}
#todayChip {{
    background: {t['surface_alt']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    color: {t['text']};
    font-size: 11px;
    padding: 2px 10px;
}}
#todayChip:hover {{ border-color: {t['accent']}; color: {t['accent']}; }}
#calendarWeekday {{
    color: {t['muted']};
    font-size: 10px;
    padding: 2px 0;
}}
#calendarDay {{
    color: {t['text']};
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px 0;
}}
#calendarDay:hover {{ background: {t['hover']}; }}
#calendarDay[holiday="true"] {{ color: {t['danger']}; }}
#calendarDay[written="true"] {{ color: {t['accent']}; }}
#calendarDay[today="true"] {{
    border-color: {t['accent']};
    color: {t['accent']};
}}

/* Settings — a grid of labelled rows, with real controls. */
#settingsKey {{ color: {t['muted']}; font-size: 12px; }}
#settingsValue {{ color: {t['text']}; font-size: 12px; }}
#segmented {{
    background: {t['surface_alt']};
    border-radius: 8px;
}}
#segmented QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {t['muted']};
    font-size: 12px;
    padding: 5px 14px;
}}
#segmented QToolButton:hover {{ color: {t['text']}; }}
#segmented QToolButton:checked {{
    background: {t['accent']};
    color: {t['on_accent']};
    font-weight: 600;
}}
#swatch {{
    background: transparent;
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 0;
}}
#swatch:checked {{ border-color: {t['text']}; }}
/* A pill that fills with the accent when on — Qt has no switch widget, so
   the knob is the button's own rounded body reading as one. */
#switch {{
    background: {t['surface_alt']};
    border: 1px solid {t['border']};
    border-radius: 12px;
}}
#switch:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}
QSlider::groove:horizontal {{
    background: {t['surface_alt']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {t['accent']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t['accent']};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}

/* Find and Replace — a card floated over the editor. */
#findPanel {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 12px;
}}
#findField {{
    background: {t['window']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
#findCaption {{ color: {t['muted']}; font-size: 11px; }}
#findCount {{ color: {t['muted']}; font-size: 11px; }}
#findInput {{
    background: transparent;
    border: none;
    color: {t['text']};
    font-size: 12px;
    padding: 0;
}}
#findStep, #findClose, #findAction {{
    background: {t['surface_alt']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    color: {t['muted']};
    font-size: 12px;
    padding: 0 10px;
}}
#findStep:hover, #findClose:hover, #findAction:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
}}
#findClose {{ background: transparent; border-color: transparent; }}
#findAction {{ color: {t['text']}; }}
#findFlag {{
    background: transparent;
    border: 1px solid {t['border']};
    border-radius: 10px;
    color: {t['muted']};
    font-size: 11px;
    padding: 3px 10px;
}}
#findFlag:hover {{ color: {t['text']}; }}
#findFlag:checked {{
    background: {t['surface_alt']};
    border-color: {t['accent']};
    color: {t['accent']};
}}

/* The reminder card, over the editor. */
#toast {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 12px;
}}
#toastTitle {{ color: {t['text']}; font-size: 12px; font-weight: 600; }}
#toastBody {{ color: {t['text']}; font-size: 13px; }}
#toastMeta {{ color: {t['muted']}; font-size: 11px; }}
#toastClose {{
    background: transparent;
    border: none;
    color: {t['muted']};
    border-radius: 6px;
    padding: 0 5px;
}}
#toastClose:hover {{ background: {t['hover']}; color: {t['text']}; }}

#paletteHeader {{ background: {t['surface']}; }}
#paletteFooter {{ background: {t['surface']}; }}
#paletteScope {{
    color: {t['muted']};
    font-size: 12px;
    font-weight: 600;
}}
#paletteInput {{
    background: transparent;
    border: none;
    color: {t['text']};
    font-size: 14px;
    padding: 0;
}}
#paletteFootnote {{ color: {t['muted']}; font-size: 11px; }}

#quickOpenList, #noteList {{
    background: transparent;
    border: none;
}}
#quickOpenList {{ padding: 8px; }}

/* Task rows are painted by ui/task_rows.py, so the sheet only owns the
   surface they sit on — no ::item rules, or they would fight the delegate. */
#taskList {{
    background: transparent;
    border: none;
    outline: none;
}}

/* My Tasks (Ctrl+T) — the same segmented control as the sidebar, so the
   two task surfaces read as one idea. */
#taskSwitch {{
    background: {t['surface_alt']};
    border-radius: 9px;
    padding: 3px;
}}
#taskSwitch QToolButton {{
    background: transparent;
    color: {t['muted']};
    border: none;
    border-radius: 7px;
    padding: 7px 16px;
    font-size: 12px;
}}
#taskSwitch QToolButton:hover {{ color: {t['text']}; }}
#taskSwitch QToolButton:checked {{
    background: {t['surface']};
    color: {t['text']};
    font-weight: 600;
}}
#taskHeading {{
    color: {t['text']};
    font-size: 21px;
    font-weight: 700;
}}
#taskSummary {{
    color: {t['muted']};
    font-size: 12px;
    border: none;
    padding: 0;
}}
#timelineHour {{
    color: {t['muted']};
    font-size: 11px;
}}
#timelineHour[now="true"] {{ color: {t['accent']}; font-weight: 600; }}
#taskCards {{
    background: transparent;
    border: none;
    outline: none;
}}
/* The detail panel closes the window on the left, on the chrome colour. */
#taskDetail {{
    background: {t['surface']};
    border-left: 1px solid {t['border']};
}}
#detailTitle {{ color: {t['text']}; font-size: 15px; }}
#detailPill {{
    border: 1px solid {t['border']};
    border-radius: 10px;
    color: {t['muted']};
    font-size: 11px;
    padding: 3px 10px;
}}
#detailRule {{ border: none; background: {t['border']}; max-height: 1px; }}
#detailKey {{ color: {t['muted']}; font-size: 12px; }}
#detailValue {{ color: {t['text']}; font-size: 12px; }}
#primaryButton {{
    background: {t['accent']};
    color: {t['on_accent']};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}
#primaryButton:hover {{ background: {t['accent_hover']}; }}
#primaryButton:disabled {{
    background: {t['surface_alt']};
    color: {t['muted']};
}}
#splitColumnCount {{
    color: {t['muted']};
    font-size: 11px;
}}
#splitColumnTitle {{
    color: {t['muted']};
    font-size: 11px;
    font-weight: 600;
    padding: 2px 4px;
}}
"""
