# Meedia Studio — Tool Architecture & Style Specification

> **Purpose:** This document codifies the patterns, conventions, and design rules extracted from the existing codebase. Any new tool tab added to Meedia Studio must follow these specifications so the app remains visually and structurally consistent.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [File & Module Layout](#2-file--module-layout)
3. [Tab Anatomy](#3-tab-anatomy)
4. [Design System (Tokens)](#4-design-system-tokens)
5. [Global Stylesheet Rules](#5-global-stylesheet-rules)
6. [Widget Library](#6-widget-library)
7. [Worker Thread Pattern](#7-worker-thread-pattern)
8. [Settings & Persistence](#8-settings--persistence)
9. [Keyboard Shortcuts](#9-keyboard-shortcuts)
10. [Naming Conventions](#10-naming-conventions)
11. [Adding a New Tool Tab — Checklist](#11-adding-a-new-tool-tab--checklist)

---

## 1. High-Level Architecture

Meedia Studio is a **PySide6 desktop application** structured as a single `QMainWindow` with a vertical (`West`) `QTabWidget`. Each tab is a *tool* — a self-contained widget that provides one media-processing capability.

```
QMainWindow  (MainWindow)
│
├── Header bar            ← App title + Settings + Refresh buttons
│
├── QTabWidget  (West, DragTabBar)
│   ├── Tab 0 — BG Remover       ← image-grid tool
│   ├── Tab 1 — AI Upscaler      ← image-grid tool
│   ├── Tab 2 — SVG Vectorizer   ← image-grid tool
│   ├── Tab 3 — Denoise & Deblur ← image-grid tool
│   ├── Tab 4 — Google Fonts     ← table-based tool (custom layout)
│   └── Tab 5 — Soundboard       ← list-based tool (self-contained widget)
│
└── Footer bar            ← Status label + Items count
```

**Two tool archetypes exist:**

| Archetype | Used by | Core widget |
|-----------|---------|-------------|
| **Image-grid tool** | BG Remover, Upscaler, Vectorizer, Denoise & Deblur | `DroppableScrollArea` + `QGridLayout` of `ImageCard` |
| **Custom-layout tool** | Google Fonts, Soundboard | Bespoke layout; no `ImageCard` |

---

## 2. File & Module Layout

```
src/
├── config.py                   # App-level constants & dependency flags
├── main_window.py              # MainWindow class — tab construction, theming, event dispatch
├── dialogs.py                  # All QDialog subclasses (confirm, compare, settings, etc.)
├── widgets.py                  # Reusable custom widgets (ImageCard, DroppableScrollArea, etc.)
├── workers.py                  # QThread subclasses for every background task
├── utils.py                    # Pure-Python helpers (paths, image conversion, vectorization)
│
├── myinstants_tab.py           # Self-contained Soundboard tab widget
├── myinstants_widgets.py       # Sound item sub-widgets used by myinstants_tab.py
├── myinstants_worker.py        # Background workers for Soundboard scraping/download
│
├── font_downloader_dialogs.py  # Dialogs specific to the Google Fonts tab
├── font_downloader_worker.py   # Background worker for font downloads
└── font_install_progress_dialog.py
```

**Rules for new tools:**

- Large, self-contained tools (like Soundboard) get their own `<tool_name>_tab.py`, `<tool_name>_worker.py`, and optionally `<tool_name>_widgets.py`.
- Simple image-grid tools add methods directly to `MainWindow` and a worker class to `workers.py`. Dialogs go in `dialogs.py`.
- Never put business logic inside `dialogs.py` or `widgets.py` — these are purely UI.

---

## 3. Tab Anatomy

### 3a. Image-Grid Tool (standard pattern)

Every image-grid tool follows this exact layout stack (top → bottom within the tab's `QVBoxLayout`):

```
QVBoxLayout (tab)
│
├── [0] Batch row  (QWidget, insertWidget at index 0)
│       QHBoxLayout
│       ├── QLineEdit  — search / filter field  (icon: search.png, leading)
│       ├── QCheckBox  — "Select All"  (objectName: "selectAllButton")
│       └── QPushButton — "Process Selected (N)"  (disabled when N=0)
│
└── [1] DroppableScrollArea  (stretch=1)
        └── QWidget  (objectName: "scrollContainer")
                └── QGridLayout  (spacing=16, margins=10,10,10,10)
                        └── ImageCard × N
```

**Key behaviours:**
- The batch row is hidden (`setVisible(False)`) when no images are loaded, shown otherwise.
- The "Process Selected" button is disabled when the selection count is 0, and its label updates to `"<Verb> Selected (N)"` on every selection change.
- Searching filters `ImageCard` visibility by filename; it does **not** remove cards from memory.
- Grid columns are computed dynamically in `populate_grid()` as `cols = max(1, scroll_width // 185)`, recalculated on every `resizeEvent`.

### 3b. Tool Tab Registration in MainWindow

1. Build the tab `QWidget` + its layout.
2. Register it: `self.tabs.addTab(widget, QIcon("res/icons/bootstrap-png/<icon>.png"), "<Label>")`.
3. Add the tool's card list: `self.<tool>_cards = []` in `__init__`.
4. Wire tool state into `_active_tab_index()`, `sc_select_all()`, `sc_process_selected()`, `sc_delete_selected()`.
5. Add card population to `load_directories()` and `populate_grid()`.
6. If the tool handles fonts/sounds (non-image), return early from `populate_grid()` for that tab index.

### 3c. Confirm Dialog Pattern

When a user clicks an `ImageCard`, the flow is always:

```
on_card_clicked_<tool>(file_path)
  │
  ├── (optional) Check dependency availability; show QMessageBox.critical if missing
  │
  ├── if settings["ask_confirm"]:
  │       <ToolConfirmDialog>(file_path, self).exec()
  │       ↓ accepted → get_settings() → update self.settings
  │
  └── launch worker → batch queue → process_next_batch_item()
```

Every confirm dialog must:
- Subclass `QDialog`
- Show a zoomable/pannable image preview (`TransparentImageLabel` inside `QScrollArea`)
- Expose a `get_settings()` method returning tool parameters
- Use standard dialog buttons ("Process" / "Cancel")

---

## 4. Design System (Tokens)

The theme is computed at runtime in `get_theme_stylesheet()` and also exposed as a consumable dict by `get_theme_colors()`. Both dark and light variants use the **same token names** — only the resolved values differ. Tokens below show the **dark mode defaults**.

### 4a. Color Tokens

#### Surface & Text tokens (both `get_theme_stylesheet()` locals and `get_theme_colors()` dict keys)

| Token | Dark default | Light default | Role |
|-------|-------------|--------------|------|
| `win_bg` | `#0f0f13` (tinted) | `#f9fafb` (tinted) | Main window & central widget background |
| `dialog_bg` | `#18181b` (tinted) | `#ffffff` | Dialog & selected tab background |
| `card_bg` | `#1e1e24` (tinted) | `#ffffff` | `ImageCard` resting background |
| `border` | `#1f2937` (tinted) | `#e5e7eb` (tinted) | Card borders, tab borders |
| `border_subtle` | `#2d2d39` (tinted) | `#d1d5db` (tinted) | Scroll area borders, separator lines |
| `text` | `#e2e8f0` | `#111827` | Body text |
| `text_muted` | `#94a3b8` (tinted) | `#4b5563` (tinted) | Secondary / placeholder text |
| `text_bright` | `#ffffff` | `#111827` | Headings, active tab label |
| `accent` | Windows DWM colour (fallback `#6366f1`) | same | Primary interactive colour |
| `accent_hover` | 85% brightness of accent | same | Button hover state |
| `accent_pressed` | 70% brightness of accent | same | Button pressed state |
| `scrollbar_handle` | `#374151` (tinted) | `#cbd5e1` (tinted) | Scrollbar handle, secondary button bg |
| `scrollbar_bg` | `#16161a` (tinted) | `#f3f4f6` (tinted) | Scrollbar track, progress bar bg |
| `input_bg` | `#1e1e24` (tinted) | `#ffffff` | QLineEdit, QComboBox background |
| `image_preview_bg` | `#0f0f13` (tinted) | `#f3f4f6` | Scroll area bg for image previews in dialogs |
| `image_preview_border` | `#2d2d39` (tinted) | `#d1d5db` (tinted) | Border for image preview scroll areas |
| `secondary_btn_bg` | `#1f2937` (tinted) | `#e5e7eb` (tinted) | Browse / secondary action button fill |
| `secondary_btn_border` | `#374151` (tinted) | `#d1d5db` (tinted) | Browse / secondary action button border |
| `secondary_btn_hover` | `#374151` (tinted) | `#d1d5db` (tinted) | Browse / secondary button hover fill |
| `menu_bg` | `#1a1a20` (tinted) | `#f9fafb` | QMenu background |
| `loading_muted` | `#888888` | `#6b7280` | Loading spinner label colour |
| `loading_subtle` | `#666666` | `#9ca3af` | Loading info sub-label colour |

#### Semantic Status tokens (same in dark & light; not accent-tinted)

| Token | Value | Role |
|-------|-------|------|
| `success` | `#059669` | Success button background |
| `success_hover` | `#047857` | Success button hover |
| `success_deep` | `#065f46` | "Apply All New" deep green |
| `success_text` | `#22b573` | Downloaded/ready filename colour |
| `warning_text` | `#fbbf24` | Warning label text |
| `error_color` | `#ef4444` | Error label text, error state |

**Accent tinting:** All surface tokens are subtly tinted toward the system accent hue via `QColor.setHsl(accent_hue, saturation, lightness)` with saturation 10–35. This ties the UI to the user's Windows accent colour.

### 4b. True Constants (not tokenized)

These values are **intentionally not theme-variable** — they are semantic constants used in painter-drawn overlays where Qt stylesheets cannot reach:

| Use | Value | Rationale |
|-----|-------|----------|
| Card processing scrim | `rgba(10, 10, 18, 170)` | Painted directly on thumbnail via `QPainter` |
| Card done scrim | `rgba(5, 46, 22, 180)` | Painted directly on thumbnail |
| Card error scrim | `rgba(60, 10, 10, 180)` | Painted directly on thumbnail |
| CardInfoBadge bg | `rgba(8, 8, 16, 200)` | `QPainter` overlay |
| CardInfoBadge top line | `rgba(99, 102, 241, 120)` | `QPainter` accent line |
| Checkerboard dark tile | `#1e1e24` | `TransparentImageLabel` QPainter tile |
| Checkerboard light tile | `#2a2a32` | `TransparentImageLabel` QPainter tile |
| Toast card bg | `#16161e` | Frameless overlay — not covered by global QSS |
| Warning banner bg | `#7f1d1d` | Intentional danger red, not accent-tinted |
| Warning banner border | `#b91c1c` | Same |
| `mono_color_btn` fill | user-chosen (dynamic) | Reflects the user's selected SVG color |

> [!TIP]
> All other colours that were previously scattered as inline hardcoded hex strings have been migrated to tokens. Use `_tc()["token_name"]` in dialogs or `.format(**_tc())` on QSS strings.

### 4c. Theme API — `get_theme_colors()` and `_tc()`

All theme tokens are accessible at runtime via two entry points:

```python
# In main_window.py (module level — usable anywhere after import)
from src.main_window import get_theme_colors
tc = get_theme_colors()   # → dict of all tokens

# In dialogs.py / any other module (zero-import convenience)
from src.dialogs import _tc
tc = _tc()   # → same dict; falls back to dark-mode defaults if called too early
```

**`get_theme_colors()`** reads the saved `settings.json` directly and the Windows DWM registry, so it is always in sync with `apply_theme()` — no `QApplication` required.

**`_tc()`** is a thin wrapper that catches import errors and returns a hardcoded dark-mode fallback dict, making it safe to call from module-level code during startup.

**Usage patterns:**

| Scenario | Pattern |
|---|---|
| Single-line `setStyleSheet` with tokens | `widget.setStyleSheet("color: {text_muted};".format(**_tc()))` |
| Multi-line triple-quoted QSS block | `widget.setStyleSheet("""...{{QSS braces}}... {token}...""".format(**_tc()))` |
| Python logic using a colour value | `_tc()["accent"]` |
| `QMenu` context menu | Inline style via `.format(**_tc())` (not covered by global QSS) |

> [!IMPORTANT]
> QSS uses `{` `}` for rule blocks. When using `.format(**_tc())`, **escape QSS braces as `{{` `}}`** and use single `{token}` for token placeholders.

### 4d. Typography

- **Font family:** `'Segoe UI', system-ui, -apple-system, sans-serif` (set on `QLabel` globally)
- **Header title (`#headerTitle`):** `font-size: 26px; font-weight: 800`
- **Dialog title (`#titleLabel`):** `font-size: 18px; font-weight: bold`
- **Section label (`#sectionTitle`):** `font-size: 13px; font-weight: bold; color: text_muted`
- **Tab label:** `font-size: 13px; font-weight: bold`
- **Card filename (`#CardName`):** `font-size: 11px; font-weight: bold`
- **Card size (`#CardSize`):** `font-size: 10px; color: text_muted`
- **Status bar:** `font-size: 12px; font-weight: 500; color: #94a3b8`
- **CardInfoBadge line 1 (dimensions):** `pointSize: 8, bold: true, color: rgba(199,210,254,240)`
- **CardInfoBadge line 2 (file size):** `pointSize: 7, bold: false, color: rgba(148,163,184,200)`
- **CardSpinner label:** `pointSize: 7, bold: true, color: rgba(199,210,254,200)`

### 4d. Spacing & Sizing

| Element | Value |
|---------|-------|
| Main layout margins | `20px` all sides |
| Main layout spacing | `16px` |
| Tab content layout margins | `10px` all sides |
| Tab content layout spacing | `12px` |
| `ImageCard` fixed size | `170 × 210 px` |
| `ImageCard` thumbnail height | `130 px` (scaled display: `140 × 110`) |
| `ImageCard` checkbox position | `(136, 8)` — absolute, top-right corner |
| Card grid spacing | `16px` |
| Card grid column width divisor | `185 px` |
| Button padding | `8px 16px` |
| Button border radius | `6px` |
| Input padding | `6px 12px` |
| Input border radius | `4px` |
| Dialog border radius | `12px` |
| Card border radius | `10px` |
| Card border width | `2px` (accent on hover) |
| Card drop shadow | `blurRadius=8, offset=(0,3), color=rgba(0,0,0,70)` |
| Tab size hint | `160 × 42 px` |
| Tab bar position | `West` (left side, vertical) |
| Toast width | `340 px` |
| Toast margin from window edge | `18 px` |
| Toast slide-in duration | `320 ms, OutCubic` |
| Toast fade-out duration | `280 ms, InCubic` |
| CardInfoBadge fade duration | `160 ms, OutCubic / InCubic` |
| CardSpinner rotation speed | `9°/tick, 25ms interval (~40 fps)` |
| CardSpinner fade-out | `400 ms, OutCubic` |
| CardSpinner done/error flash | `16 ticks (~400 ms)` |

---

## 5. Global Stylesheet Rules

The stylesheet is applied globally via `QApplication.instance().setStyleSheet(...)` and covers all standard Qt widgets. **Do not re-apply the base styles locally on individual widgets** — they are already inherited.

### Covered Widget Types (auto-styled)

`QMainWindow`, `QWidget#central`, `QScrollArea`, `#scrollContainer`, `QScrollBar` (vertical + horizontal), `QPushButton`, `QDialog`, `QLabel`, `QProgressBar`, `QTabWidget::pane`, `QTabBar::tab`, `QComboBox`, `QSlider`, `QLineEdit`, `#ImageCard`, `#CardName`, `#CardSize`

### Overridable Object Names (QSS selectors)

| Selector | Description |
|----------|-------------|
| `QWidget#central` | Central widget |
| `#scrollContainer` | Inner widget of every `DroppableScrollArea` |
| `#ImageCard` | Image card resting state |
| `#ImageCard:hover` | Image card hover state |
| `#CardName` | Card filename label |
| `#CardSize` | Card file size label |
| `QLabel#headerTitle` | App title in the header |
| `QLabel#titleLabel` | Dialog title |
| `QLabel#sectionTitle` | Section grouping label |
| `QPushButton#selectAllButton` | The "Select All" checkbox-style button (uses `scrollbar_handle` bg) |
| `QPushButton#cancelButton` | Secondary/cancel button style |
| `QPushButton#secondaryButton` | Browse / secondary action buttons (uses `secondary_btn_*` tokens) |
| `QLabel#statusLabel` | Status bar and items-count labels |
| `QLabel#errorLabel` | Error state label (uses `error_color` token) |
| `QLabel#loadingLabel` | Loading spinner label (uses `loading_muted` token) |
| `QLabel#loadingInfoLabel` | Loading sub-label (uses `loading_subtle` token) |
| `QWidget#warningBanner` | rembg missing dependency banner (danger red — intentional constant) |

### Inline Styles (allowed exceptions)

Inline `setStyleSheet()` is still used in a few cases where the global QSS cannot reach. **All must use token values via `.format(**_tc())`** — no bare hex literals.

1. **Context menus** — `QMenu` is not in global QSS scope. Use:
   ```python
   menu.setStyleSheet(
       "QMenu {{ background-color: {menu_bg}; color: {text}; border: 1px solid {scrollbar_handle}; ... }}"
       " QMenu::item:selected {{ background-color: {accent}; color: {text_bright}; }}".format(**_get_tc())
   )
   ```
2. **Toast notifications** — `ToastNotification` is a frameless overlay. Severity accent colours (`success`, `error_color`, `warning_text`, `accent`) are read from `_tc()`.
3. **Drag highlight** — `DroppableScrollArea._set_drag_highlight()` uses hardcoded indigo (`#6366f1`) — intentional constant, not theme-variable.
4. **Warning banner** — Uses `#warningBanner` objectName (covered by global QSS). The danger-red values are intentional constants.
5. **Google Fonts table** — `QTableWidget` inline style reads `scrollbar_handle` and `border_subtle` from `_tc()`.
6. **Dialog form widgets** — `QComboBox`, `QSlider`, `QLineEdit`, `QSpinBox` inside dialogs use inline styles with `.format(**_tc())` since QSS inheritance from parent dialogs is unreliable.
7. **`mono_color_btn`** — Background is the user-chosen SVG colour (dynamic); only border uses `_tc()["scrollbar_handle"]`.

---

## 6. Widget Library

All reusable widgets live in `src/widgets.py`. Prefer these over custom implementations.

### `DragTabBar(QTabBar)`
Custom tab bar used as `self.tabs.setTabBar(DragTabBar(self.tabs))`. Fixes tab text to left-aligned horizontal rendering even with `West` tab position (via `LeftAlignTabProxy` style). Tab size hint: `160 × 42 px`. Cursor: `PointingHandCursor`.

### `DroppableScrollArea(QScrollArea)`
Accepts file drag-and-drop from Windows Explorer. Emits `files_dropped(list[str])` with valid image paths.  
Valid extensions: `.png .jpg .jpeg .webp .svg`  
Drag highlight: `2px dashed #6366f1` border, `rgba(99,102,241,0.06)` fill.

### `ImageCard(QFrame)`
Fixed `170 × 210 px` card displaying an image thumbnail. Key features:

| Attribute | Detail |
|-----------|--------|
| `objectName` | `"ImageCard"` (QSS theming) |
| `card_type` | `'bg'`, `'up'`, `'vec'`, `'rest'` |
| `file_path` | Absolute path to the image file |
| `checkbox` | `QCheckBox`, absolute pos `(136, 8)` |
| Click behaviour | Single-click emits `clicked(str)` if nothing selected; toggles checkbox if selections active |
| Drag | Exports file via `QDrag` + `Qt.CopyAction`; drag pixmap scaled to `70×70` |
| Hover enter | Calls `set_status(file_path)` on MainWindow; shows `CardInfoBadge` |
| Hover leave | Resets status; fades out `CardInfoBadge` |
| Processing | `set_processing(True)` → creates/shows `CardSpinner`; `set_processing(False)` → calls `mark_done()` |
| Error | `set_error()` → calls `mark_error()` on spinner |

### `CardInfoBadge(QWidget)`
Frosted-glass pill at the bottom of the thumbnail (height `42 px`, full thumbnail width). Rendered purely via `QPainter`. Shows:
- Line 1: `W × H px` — `pointSize=8, bold, color=rgba(199,210,254,240)`
- Line 2: `X.X KB` — `pointSize=7, color=rgba(148,163,184,200)`
- Background: `rgba(8, 8, 16, 200)`, radius `7`
- Top accent line: `rgba(99, 102, 241, 120)`

Fade animation: `QGraphicsOpacityEffect` + `QPropertyAnimation`, 160 ms `OutCubic`/`InCubic`.

### `CardSpinner(QWidget)`
Transparent overlay over the thumbnail area during processing. Three states:

| State | Visual | Trigger |
|-------|--------|---------|
| `'processing'` | Spinning indigo arc, 270° sweep, dark scrim | `set_processing(True)` |
| `'done'` | Green circle + checkmark, 16-tick flash, then fade | `mark_done()` |
| `'error'` | Red circle + X, 16-tick flash, then fade | `mark_error()` |

Arc colour: `rgba(129, 140, 248, 230)` (indigo-400). Track: `rgba(99, 102, 241, 50)`. Fade: `QPropertyAnimation` 400 ms `OutCubic`.

### `ToastNotification(QWidget)`
Call via `MainWindow.show_toast(message, severity, duration_ms=3500)`.

| Severity | Border / icon colour | Text colour |
|----------|---------------------|-------------|
| `'success'` | `#10b981` | `#6ee7b7` |
| `'error'` | `#f43f5e` | `#fda4af` |
| `'warning'` | `#f59e0b` | `#fcd34d` |
| `'info'` | `#6366f1` | `#a5b4fc` |

Structure: card `QFrame` with `border-left: 4px solid {accent}`, icon label, message label, close button, countdown `QProgressBar` (3 px height).

### `TransparentImageLabel(QLabel)`
Used inside confirm dialog scroll areas. Renders a 10×10 dark checkerboard (`#1e1e24` / `#2a2a32`) behind transparent PNGs. Supports zoom via `set_zoom(factor)`. Initial fixed size: `400 × 360 px`.

### `TransparentSvgLabel(QWidget)`
Same checkerboard, renders SVG via `QSvgRenderer`. Used in vectorizer comparison dialogs.

### `RegionSelectLabel(QLabel)`
Interactive rubber-band region selector for the Restoration confirm dialog. Emits `region_selected(QRect)` in original image pixel coordinates (corrects for aspect-ratio letterboxing). Selection drawn as `2px dashed #6366f1` with `rgba(99,102,241,40)` fill.

---

## 7. Worker Thread Pattern

All background processing uses `QThread` subclasses defined in `src/workers.py`.

### Signal Signatures

| Worker | `finished` signal |
|--------|-------------------|
| `FileDownloadWorker(url, dest_path)` | `progress(int, int, int)`, `finished(bool, str)` |
| `BGRemovalWorker(image_path, model_name)` | `finished(bool, PIL.Image, str)` |
| `UpscaleWorker(image_path, model_name, scale)` | `finished(bool, PIL.Image, str)` |
| `VectorizerWorker(image_path, mode, num_colors, tolerance, mono_color)` | `finished(bool, str svg, str)` |
| `RestorationWorker(image_path, params_dict)` | `finished(bool, PIL.Image, str)` |

### Worker Lifecycle Contract

```python
# 1. Create worker with all needed params
worker = MyToolWorker(image_path, param1, param2)

# 2. Connect signals before starting
worker.finished.connect(self.on_my_tool_finished)

# 3. Show spinner on the card
card.set_processing(True)

# 4. Start worker thread
worker.start()

# 5. In the finished slot (runs on main thread):
def on_my_tool_finished(self, success, result, error):
    card.set_processing(False)   # triggers green-tick flash
    if not success:
        card.set_error()
        self.show_toast(f"Failed: {error}", 'error')
        return
    # save result to disk, refresh gallery
    self.load_directories(self.current_dirs)
    self.show_toast("Done!", 'success')
```

**Rules:**
- Workers never touch Qt widgets directly. All UI updates happen in connected slots on the main thread.
- The entire `run()` body must be wrapped in `try/except Exception as e` and always emit `finished`.
- Workers are started with `.start()`, not `.run()`.

### Batch Queue Pattern

Used for "Process Selected (N)" operations:

```python
self.active_tool = '<prefix>'
self.batch_queue  = [card.file_path for card in selected_cards]
self.batch_results = []
self.batch_total   = len(self.batch_queue)
self.process_next_batch_item()

def process_next_batch_item(self):
    if not self.batch_queue:
        self.on_batch_complete()
        return
    path = self.batch_queue.pop(0)
    worker = MyToolWorker(path, ...)
    worker.finished.connect(self.on_single_item_finished)
    worker.start()

def on_single_item_finished(self, success, result, error):
    # record result; update card state
    self.process_next_batch_item()   # chain next item
```

---

## 8. Settings & Persistence

### Storage Location

`%LOCALAPPDATA%\RPSoft\MeediaStudio\settings.json` (resolved by `utils.get_app_data_dir()`).

### Default Schema (v1)

```json
{
    "model_name": "u2net",
    "ask_confirm": true,
    "primary_folder": "",
    "theme_mode": "Dark"
}
```

`theme_mode` accepts: `"Dark"` | `"Light"` | `"Auto (System)"`.

### Rules for New Settings

1. Add key + default to `self.settings` dict in `load_app_settings()`.
2. Expose a UI control in `SettingsDialog` in `dialogs.py`.
3. Read with `self.settings.get("my_key", default_value)`.
4. Call `self.save_app_settings()` after any user-confirmed change.

### Model / Asset Files

Large binary assets (AI models, executables) are stored under:
`get_app_data_dir() / models / <tool_name> /`

Downloads use `FileDownloadWorker` with a `LoadingDialog` that shows a progress bar and cancel button.

---

## 9. Keyboard Shortcuts

Registered in `_register_shortcuts()` with `Qt.WindowShortcut` scope (active regardless of focused widget).

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open file picker; copy chosen images into primary dir; refresh |
| `Ctrl+A` | Toggle Select All on the active image-grid tab |
| `Delete` | Delete checked cards on active tab (soft-delete to `.undo_trash/`) |
| `Ctrl+Z` | Undo last batch delete (restore from `.undo_trash/`) |
| `Ctrl+S` | Process selected items on the active tab |

**Undo implementation:** Files are moved (not deleted) to `<project_root>/.undo_trash/<id>_<filename>`. Stack stores `[(original_path, backup_path), ...]` per batch operation, bounded to the last 10 batches.

**Routing:** `_active_tab_index()` returns `0–3` for image-grid tabs, `-1` for non-image tabs (Fonts, Soundboard). All shortcut handlers branch on this index.

---

## 10. Naming Conventions

### Python Identifiers

| Entity | Convention | Example |
|--------|-----------|---------|
| Module file | `snake_case` | `myinstants_tab.py` |
| Class | `PascalCase` | `ImageCard`, `BGRemovalWorker` |
| Method | `snake_case` | `on_card_clicked_bg` |
| Signal handler | `on_<source>_<event>` | `on_tab_changed`, `on_fonts_sort_changed` |
| Private method/attr | `_snake_case` | `_active_tab_index`, `_set_drag_highlight` |
| Worker class | `<Action>Worker` | `UpscaleWorker`, `RestorationWorker` |

### MainWindow Attribute Prefixes

Image-grid tools follow a strict two/three-letter prefix so code is immediately parseable:

| Attribute | Pattern | Prefixes in use |
|-----------|---------|-----------------|
| Tab widget | `self.<p>_tab` | `bg`, `up` (upscaler), `vec`, `rest` |
| Scroll area | `self.<p>_scroll_area` | same |
| Scroll widget | `self.<p>_scroll_widget` | same |
| Grid layout | `self.<p>_grid_layout` | same |
| Batch row | `self.<p>_batch_row` | same |
| Search field | `self.<p>_search` | same |
| Select All checkbox | `self.<p>_btn_select_all` | same |
| Batch action button | `self.<p>_btn_batch` | same |
| Card list | `self.<prefix>_cards` | `bg_cards`, `upscaler_cards`, `vectorizer_cards`, `restoration_cards` |

> Note: the card list uses a longer suffix (`upscaler_cards`, `vectorizer_cards`) for readability, unlike the shorter tab-widget prefix.

### QSS Object Names

| objectName | Widget type | Purpose |
|------------|-------------|---------|
| `"central"` | `QWidget` | Main window central widget |
| `"mainTabs"` | `QTabWidget` | Root tab widget |
| `"scrollContainer"` | `QWidget` | Inner widget of DroppableScrollArea |
| `"ImageCard"` | `QFrame` | Image card (theming via QSS) |
| `"CardName"` | `QLabel` | Card filename label |
| `"CardSize"` | `QLabel` | Card file size label |
| `"headerTitle"` | `QLabel` | App title |
| `"titleLabel"` | `QLabel` | Dialog title |
| `"sectionTitle"` | `QLabel` | Section heading |
| `"selectAllButton"` | `QPushButton` | Select All (secondary muted style) |
| `"cancelButton"` | `QPushButton` | Cancel / secondary action button |
| `"ToastCard"` | `QFrame` | Toast notification card |
| `"cardCheckbox"` | `QCheckBox` | Per-card selection checkbox |

### Icon Files

All icons are Bootstrap Icons PNGs at `res/icons/bootstrap-png/<name>.png`.  
Load with `QIcon("res/icons/bootstrap-png/<name>.png")` (relative to `main.py` cwd).

Currently used icons: `person-bounding-box`, `arrows-angle-expand`, `vector-pen`, `magic`, `fonts`, `boombox`, `gear`, `arrow-clockwise`, `search`, `folder2-open`, `download`, `pc-display`, `play-fill`.

---

## 11. Adding a New Tool Tab — Checklist

Use this as a step-by-step guide when implementing any new image-grid tool.

### Step 1 — Worker (`src/workers.py`)

- [ ] Create `class <Tool>Worker(QThread):`
- [ ] Define `finished = Signal(bool, <ResultType>, str)`
- [ ] Accept all processing params in `__init__`
- [ ] Wrap entire `run()` body in `try/except Exception as e: self.finished.emit(False, None, str(e))`

### Step 2 — Confirm Dialog (`src/dialogs.py`)

- [ ] Create `class <Tool>ConfirmDialog(QDialog):`
- [ ] Show `TransparentImageLabel` in a `QScrollArea` with pan/zoom support
- [ ] Include tool-specific options (combos, sliders, checkboxes)
- [ ] Implement `get_settings() -> <params>` method
- [ ] Use "Process" / "Cancel" button layout

### Step 3 — Tab Widget (`src/main_window.py`, `__init__`)

- [ ] Declare `self.<p>_cards = []`
- [ ] Declare tool state: `self.<tool>_<param> = <default>`
- [ ] Create `self.<p>_tab = QWidget()` + `QVBoxLayout`
- [ ] Create `DroppableScrollArea` + inner `QWidget(objectName="scrollContainer")` + `QGridLayout(spacing=16, margins=10,10,10,10)`
- [ ] Connect `files_dropped` → `self.on_files_dropped`
- [ ] Create batch row: `search QLineEdit` + `Select All QCheckBox(objectName="selectAllButton")` + `batch QPushButton`
- [ ] Set batch row `setVisible(False)` initially; `insertWidget(0, ...)` to pin it at top
- [ ] Register: `self.tabs.addTab(self.<p>_tab, QIcon("res/icons/bootstrap-png/<icon>.png"), "<Label>")`

### Step 4 — Wire into existing methods (`src/main_window.py`)

- [ ] `_active_tab_index()` — add `elif idx == N` for new tab index (if it's an image-grid tab)
- [ ] `sc_select_all()` — add `elif tab == N: self.select_all_<p>()`
- [ ] `sc_process_selected()` — add `elif tab == N: self.on_process_selected_<p>()`
- [ ] `sc_delete_selected()` — add `N: self.<p>_cards` to the `card_lists` dict
- [ ] `load_directories()` — clear `self.<p>_cards`; create `ImageCard` per image path; set `card_type`; connect signals; toggle batch row
- [ ] `populate_grid()` — add grid population loop for `self.<p>_cards`

### Step 5 — Add helper methods

- [ ] `filter_<p>_grid(text)` — filter card visibility by filename
- [ ] `select_all_<p>()` — toggle all visible cards
- [ ] `update_batch_button_<p>()` — update count label and enabled state
- [ ] `has_active_selections_<p>()` — return bool for any checked card
- [ ] `on_card_clicked_<p>(file_path)` — confirm dialog → start single-item worker
- [ ] `on_process_selected_<p>()` — gather checked cards → batch queue
- [ ] `on_<p>_result(success, result, error)` — handle worker finish, save output, toast, refresh

### Step 6 — Wire `ImageCard` routing

- [ ] In `load_directories()`: set `card.<p>_type = '<p>'`; connect `clicked` and `selection_changed`
- [ ] In `widgets.py ImageCard.parent_window_has_selections()`: add `elif card_type == '<p>'` branch

### Step 7 — Style conformance checklist

- [ ] Tab icon is from `res/icons/bootstrap-png/`
- [ ] No hardcoded colours outside the approved semantic palette
- [ ] Button text updates dynamically: `"<Verb> Selected (N)"`
- [ ] Batch button disabled when `N == 0`
- [ ] Search filters visibility only (no memory removal)
- [ ] Worker always emits `finished` even on exception
- [ ] Card shows `set_processing(True)` → `set_processing(False)` or `set_error()`
- [ ] Results communicated via `show_toast()` (non-blocking)
- [ ] Heavy confirmation respects `settings["ask_confirm"]`
- [ ] Confirm dialog shows zoomable image preview
