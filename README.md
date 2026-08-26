# Notepad Plus

A fast, minimal text editor for Windows with first-class support for both
English and Persian text. Built to replace Windows Notepad: it opens fast,
stays out of the way, and keeps every note as a plain `.txt` / `.md` file.

## Features

**Writing**

- Tabbed editing with rename, reopen closed tab (`Ctrl+Shift+T`) and drag & drop
- **Right-to-left by default** — the whole document stays on one side instead of
  flipping per paragraph. `Ctrl+Right Shift` / `Ctrl+Left Shift` switches it, and
  the choice is remembered per file
- Smart bullet, numbered and to-do lists with automatic continuation,
  indentation and clickable checkboxes (`Ctrl+Shift+7/8/9`)
- Headings (`Ctrl+1/2/3`), bold (`Ctrl+B`) and live Markdown styling — the
  markers are hidden on screen but the file stays standard Markdown
- Separate font choices for English and Persian text, so one script never
  forces a compromise on the other
- Lines inside a ``` fence render in monospace and stay left-to-right, and
  `Ctrl+Shift+C` wraps the selection in one

**Tasks**

- Any checkbox becomes a dated task by ending it with an `@` stamp:
  `- [ ] تحویل سایت @1405/06/05 10:00`. The file stays plain Markdown, so a
  task is never locked inside this app
- Both calendars are accepted — a year below 1600 is read as Jalali, above it
  as Gregorian — and Persian digits work: `@۱۴۰۵/۰۶/۰۵`
- **`Ctrl+T` — my tasks.** Every unfinished dated item across the notes
  folder, in three readings: a list grouped overdue / today / tomorrow /
  later, a today-and-ahead split, and a timeline of the day. Selecting one
  opens the note at that line; "تعویق به فردا" pushes it a day
- **Repeating tasks.** A `↻` after the stamp (`Ctrl+Shift+R`) makes a task
  weekly, so a missed one moves to next week instead of sitting overdue
  forever. `Ctrl+Shift+A` stamps a task with today's date
- **`Ctrl+Shift+D` — today's note.** One file per day under `Daily`, named
  `1405-06-04.md` so it sorts, headed in Persian so it reads
- A Jalali month calendar in the sidebar: days you have written are marked,
  clicking one opens that day, with the week ahead summarised below it
- Today's progress sits at the end of the tab strip, and stays out of the way
  on a day with nothing scheduled
- Windows notifications when a task comes due, from the tray. Each reminder
  fires once; editing the task's text or date makes it a new one
- Upcoming reminders are also registered with Windows Task Scheduler, so they
  still arrive when the editor is closed. Turn it off in Settings; uninstalling
  removes them

**Finding things**

- **`Ctrl+P` — go to anything.** Type a few letters and press Enter. Notes
  come first (a folder name finds the notes inside it too), then whatever is
  still open on your task list, then commands
- Sidebar (`Ctrl+Shift+B`) with three panes behind one switch — notes with
  full-text search, open tasks by urgency, and the calendar
- Find and Replace with match case, whole word, wrap around (`F3` / `Shift+F3`)
- Go To Line (`Ctrl+G`)

**Keeping your work**

- Atomic writes, crash recovery, and a warning when a file changes on disk
  outside the editor
- Encoding detection and control: UTF-8, UTF-8 BOM, UTF-16 LE/BE, Windows-1256/1252
- Export to PDF, HTML and Markdown

**Everything else**

- Dark / Light / System themes, in three colour sets — Graphite, Ink & Amber
  and Slate & Violet. Every colour in the app comes from one of eleven tokens,
  so the whole interface changes together
- Toggleable line numbers; word wrap
- Zoom with `Ctrl+=` / `Ctrl+-` / `Ctrl+0` or Ctrl+mouse wheel
- Time/Date (`F5`), word and character count in the status bar
- Clickable status-bar chips for encoding and text direction
- Settings (`Ctrl+,`): theme, fonts (with custom `.ttf`/`.otf` install), font
  size, word wrap, default text direction, default save folder
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
python -m PyInstaller --clean --noconfirm notepad.spec   # → dist\NotepadPlus\NotepadPlus.exe
ISCC.exe installer.iss                                   # → dist\NotepadPlus-Setup-3.7.0.exe
dist\NotepadPlus\NotepadPlus.exe --smoke-test            # packaged startup check; exits with code 0
```

`ISCC.exe` ships with Inno Setup; if it is not on `PATH` it is usually at
`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

The installer adds Start Menu/desktop shortcuts and an "Open with" entry for
`.txt`/`.md` files. The `dist\NotepadPlus` folder works as the portable build.

> Run the built exe from a short path. Deep folders can exceed the Windows path
> limit while Qt loads its DLLs, and the app then shows an error dialog instead
> of starting.

## Deliberately not included

Removed in 3.1 to keep the editor quick and quiet, after they proved to cost
more than they returned:

- **Guessing at unfenced code, and syntax highlighting.** It scanned the whole
  document on every keystroke and misread ordinary notes — anything with a
  colon, a bracket or an equals sign — as code, forcing those lines
  left-to-right. Only an explicit ``` fence marks code now.
- **Word (.docx) export**, which pulled in `python-docx` and `lxml`.
- **The Markdown preview pane**, made redundant by the live styling.
- **Tags and pins** (3.0), which had to be maintained by hand and so never were.
  Folders do the job and are visible in Explorer too.
