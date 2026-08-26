# Notepad Plus — UI design brief

A design brief for redrawing the interface. Everything below describes the
app **as it exists today** (v3.6.0), not a wish list.

---

## What it is

A Windows desktop text editor for a **Persian-speaking freelance web
developer**. It replaces Windows Notepad for daily use and doubles as a
lightweight task manager. Every note is an ordinary `.txt` / `.md` file in
`Documents\Notepad` — nothing is locked in a database.

**Three things it is judged on, in order:**

1. **Speed.** Typing costs 2.2 ms per keystroke on a 6,000-line file; launch
   is ~1.6 s. No design may add work to either.
2. **Right-to-left first.** Documents open RTL by default and the whole
   document stays on one side. Persian is the primary language of the
   content; the interface chrome is currently English.
3. **Quiet.** Features that could not justify themselves were deliberately
   removed (syntax highlighting, Word export, a preview pane, tags). The
   design should not reintroduce visual noise.

**Not wanted:** dashboards, avatars, onboarding, gradients-for-their-own-sake,
anything that looks like a web app.

---

## Technical constraints — please read

- **Qt 6 widgets (PyQt6), styled with Qt Style Sheets.** A subset of CSS:
  `background`, `color`, `border`, `border-radius`, `padding`, `margin`,
  `font-*`, `min/max-width/height`, and pseudo-states (`:hover`, `:selected`,
  `:checked`, `:focus`) all work.
- **Not available:** flexbox, grid, CSS transitions or animations,
  `box-shadow`, `transform`, `opacity` on widgets, web fonts, SVG in
  stylesheets. Layout is done in code with box layouts, not CSS.
- Anything custom-drawn (list bullets, checkboxes, calendar cells) is painted
  manually, so unusual shapes are possible but each one costs code.
- **Icons:** there are none today — the toolbar uses text glyphs
  (`B`, `H1`, `•`, `1.`, `☑`). Proposing a small icon set is welcome; it
  would ship as SVG files rendered to `QIcon`.
- Two themes, switchable at runtime plus a "System" option that follows
  Windows.

---

## Current colour tokens

Every colour in the app comes from one of these. A redesign should return the
same token names with new values, so nothing else has to change.

| token | dark | light | used for |
|---|---|---|---|
| `window` | `#212128` | `#f9fafc` | editor background, window body |
| `surface` | `#2b2b33` | `#ffffff` | menu bar, tabs, status bar, sidebar |
| `surface_alt` | `#33333d` | `#eef1f6` | inputs, buttons, code block tint |
| `hover` | `#3a3a45` | `#e6eaf1` | hover states |
| `border` | `#42424e` | `#d9dde6` | all borders and separators |
| `text` | `#e7e8ec` | `#1f2329` | body text |
| `muted` | `#989aa6` | `#71798a` | secondary labels, line numbers |
| `accent` | `#4cc2ff` | `#0067c0` | selection, active tab, markers, today |
| `accent_hover` | `#73d1ff` | `#005aa8` | accent hover |
| `on_accent` | `#10131a` | `#ffffff` | text on an accent fill |
| `danger` | `#ff6b78` | `#d84254` | overdue tasks, Fridays, destructive |

**Typography:** Inter (4 weights) for Latin, Vazirmatn (2 weights) for
Persian, bundled with the app. The two are chosen separately in Settings and
resolved per character, so one line can contain both. Code uses Cascadia
Mono / Consolas. Editor default is 14 pt; UI is 10 pt.

---

## Surfaces to design

### 1. Main window — the one that matters

Default 1060 × 720, minimum 720 × 480. Top to bottom:

- **Menu bar** — File, Edit, Format, View, Help
- **Format toolbar** — a thin strip: `B` · `H1` `H2` `H3` · `•` `1.` `☑`
- **Tab bar** — document tabs, closable, draggable, with a `+` button after
  the last tab. A modified tab shows a `●` before its name.
- **Sidebar** (toggleable, can sit left or right) containing, top to bottom:
  - folder name + "Change folder" button
  - a search box (searches file names first, then file contents)
  - **a Jalali month calendar** — see below
  - a tree of notes grouped by subfolder
- **Editor** — the main area. Line numbers in a left gutter.
- **Status bar** — `Ln 1, Col 1` · `1,234 words · 5,678 characters` · `100%` ·
  `UTF-8` (clickable) · `RTL · Auto` (clickable) · `Saved` / `Unsaved`

**The editor renders Markdown live while keeping the file plain text:**
- Headings are larger and bold; the `#` markers are invisible on screen
- `**bold**` renders bold with the asterisks hidden
- `- ` bullets are drawn as a round dot in the accent colour
- `1.` numbered items get a fixed gutter and show **Persian digits** in an
  RTL paragraph, with the dot to the *left* of the digit
- `- [ ]` is drawn as a real checkbox you can click; a done item is struck
  through and muted
- Lines inside a ``` fence are monospace with a tinted background

### 2. Sidebar calendar

A compact Jalali month grid. **The week starts on Saturday** (`ش ی د س چ پ ج`).
Header: month name + year, back/forward arrows, a "امروز" (today) chip.
Fridays are in `danger`. Today has an accent outline. Days that already have
a note are accent-coloured and bold. Clicking a day opens that day's note.

### 3. `Ctrl+P` — Go to File

A modal, 560 px wide. A text field, a result list below, a count line at the
bottom. Type a few letters of a file name; folder names match too. Arrow keys
move, Enter opens. **This should feel instant and keyboard-only.**

### 4. `Ctrl+T` — My Tasks

A modal, 620 × 460, laid out right-to-left. A large Persian date heading
(`۴ شهریور ۱۴۰۵`), then a tree grouped into **عقب‌افتاده / امروز / فردا /
بعداً / بدون تاریخ**. Each row is the task text and its due date; overdue rows
are in `danger`. A summary line: `۴ کار باز · ۲ عقب‌افتاده · ۱ برای امروز`.
Clicking a task opens its note at that line.

*This screen has the most room for improvement — it is currently a plain tree
and could read much more like a real task list.*

### 5. Settings — `Ctrl+,`

440 px wide, two groups:
- **Appearance:** theme, English font, Persian font (+ "Install…" button),
  font size
- **Files:** text direction, "remind me when closed", word wrap, default save
  folder

### 6. Smaller surfaces

- **Find and Replace** — non-modal, 420 px: two fields, three checkboxes
  (match case, whole word, wrap around), four buttons
- **Keyboard shortcuts** — a reference list, ~30 entries
- **Tray notification** — title + up to four task lines
- **About**

---

## What a task looks like

A task is a Markdown checkbox with a date stamp appended:

```markdown
- [ ] تحویل سایت بامسما @۱۴۰۵/۰۶/۰۵ ۱۰:۰۰
- [x] تماس با مشتری @1405/06/03
- [ ] یادداشت بدون تاریخ
```

Both calendars parse (a year under 1600 is Jalali), and Persian digits work.
The design should make a dated task visibly different from a plain one **in
the editor**, without hiding the underlying text — today the date stamp is
just part of the line.

---

## Where the design is weakest today

Ranked, most valuable first:

1. **My Tasks (Ctrl+T)** reads like a file tree, not a task list. No sense of
   priority, no breathing room, dates are plain text.
2. **The format toolbar** is text glyphs on a grey strip. It looks unfinished.
3. **The status bar** shows six items with equal weight; nothing stands out
   and the two clickable chips do not look clickable.
4. **The sidebar** stacks four unrelated things (folder, search, calendar,
   tree) with no visual separation.
5. **Density.** Padding is inconsistent between the sidebar, dialogs and the
   toolbar. A single spacing scale would fix most of it.
6. **No icons anywhere**, including the tab bar and toolbar.

---

## What to deliver

1. Dark and light values for the eleven tokens above.
2. A spacing and radius scale.
3. Mockups of: the main window (sidebar open, a note with a checklist and a
   code block), My Tasks, Go to File, and the sidebar calendar.
4. Optionally, a small icon set (~15 glyphs) as SVG.

Keep it minimal and quiet. This is a tool someone stares at for hours, in
Persian, mostly on a dark screen.
