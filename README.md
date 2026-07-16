# Notepad Plus

A fast, minimal text editor for Windows with first-class support for both
English and Persian text. English UI, Windows Notepad feature set, plus a few
extras that stay out of your way.

## Features

- Tabbed editing with rename, reopen closed tab (`Ctrl+Shift+T`) and drag & drop
- True file open/save for TXT and Markdown, atomic writes, crash recovery
- Encoding detection and control: UTF-8, UTF-8 BOM, UTF-16 LE/BE, Windows-1256/1252
- Automatic per-paragraph RTL/LTR direction; `Ctrl+Right Shift` / `Ctrl+Left Shift`
  to override, exactly like native Windows text fields
- **Smart bullet, numbered and to-do lists** with automatic continuation,
  indentation and clear clickable checkboxes (`Ctrl+Shift+7/8/9`)
- **Headings** (`Ctrl+1/2/3`) and live Markdown styling
- Code block detection (fenced and heuristic) with one-click copy
- Find and Replace with match case, whole word, wrap around, `F3`/`Shift+F3`
- Go To Line (`Ctrl+G`), Time/Date (`F5`), word and character count in the status bar
- Zoom with `Ctrl+=`/`Ctrl+-`/`Ctrl+0` or Ctrl+mouse wheel, shown as a percentage
- Dark / Light / System themes; toggleable line numbers
- Optional notes sidebar (`Ctrl+B`) with search, pins and tags — single click opens
- Export to PDF, Word (.docx), HTML and Markdown
- Quick formatting bar (H1 H2 H3 · bullet · to-do) like Windows Notepad
- Clickable status-bar chips for encoding and text direction
- Settings window (`Ctrl+,`): theme, font (with custom .ttf/.otf install),
  font size, word wrap, default save folder
- Keyboard shortcuts reference under Help (`Ctrl+/`)

Files are saved to `Documents\Notepad` by default; change the folder in Settings.
App settings and recovery snapshots live in the user's AppData.

## Run from source

```powershell
python main.py
```

## Test

```powershell
python -m pytest -q
```

## Build

```powershell
python -m PyInstaller --clean --noconfirm notepad.spec   # → dist\NotepadPlus.exe (portable)
ISCC.exe installer.iss                                   # → dist\NotepadPlus-Setup-2.2.0.exe
```

The installer adds Start Menu/desktop shortcuts and an "Open with" entry for
`.txt`/`.md` files. The portable exe works standalone with no installation.
