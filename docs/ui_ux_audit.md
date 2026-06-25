# Meedia Studio — UI/UX & Production Readiness Audit

**Auditor:** Senior UI/UX Engineer / PySide6 Desktop Specialist  
**Scope:** Full codebase — layouts, styling, widgets, dialogs, concurrency, interaction patterns, accessibility, code quality  
**Files Reviewed:** `main.py`, `src/main_window.py` (4278 lines), `src/widgets.py` (1498 lines), `src/dialogs.py` (3044 lines), `src/tts_tab.py`, `src/ytdlp_tab.py`, `src/command_palette.py`, `src/utils.py`, `src/config.py`, `src/workers.py`, `src/browser_tab.py`, and supporting dialog files  

---

## Executive Summary

Meedia Studio is a functionally capable desktop AI toolkit with a coherent visual identity and a sophisticated theme system. The concurrency architecture is sound — heavy work is consistently pushed to background threads. However, the codebase has accumulated significant technical debt in its UI layer: duplicate class definitions, broken coordinate logic, layout instability patterns, hardcoded color values that bypass the theme system, inconsistent styling between equivalent components, and a critical structural defect in `widgets.py` that duplicates entire class bodies.

The most urgent issues are correctness bugs (the dead `mouseReleaseEvent` in `RegionSelectLabel`) and structural duplications that create maintenance hazards. Secondary issues include theme-system violations, dialog layout inconsistencies, and missing accessibility attributes.

---

## Severity Reference

| Level | Definition |
|---|---|
| **Critical** | Functional breakage, data loss risk, or crash potential |
| **High** | Visible user-facing defect; incorrect behavior during normal use |
| **Medium** | Inconsistency, minor UX friction, or policy violation |
| **Low** | Polish, cleanup, or optimization opportunity |

---

## 1. Critical Issues

### C-1 — Dead Code in `RegionSelectLabel.mouseReleaseEvent` (widgets.py) ✅

**Location:** `src/widgets.py`, `RegionSelectLabel` (first definition, lines 1093–1166)

**Problem:** The `mouseReleaseEvent` method computes `orig_x`, `orig_y`, `orig_w`, `orig_h` from the selection rectangle, then on line 1166 executes:

```python
return self._img_dims
```

This is dead code — it references `self._img_dims`, which is not defined on this class. The computed region coordinates are never emitted via `self.region_selected`. The `region_selected` signal defined on line 1094 is therefore **never fired** from this instance.

**User Impact:** Any dialog or tool relying on `RegionSelectLabel.region_selected` (the denoise/deblur region selection feature) silently does nothing. The user can draw a selection rectangle but no event fires.

**Technical Cause:** A merge or edit introduced a stray `return self._img_dims` that terminates the function before `self.region_selected.emit(...)`.

**Fix:**

```python
# Remove:
return self._img_dims

# Add (mirroring the second definition):
self.region_selected.emit(QRect(orig_x, orig_y, orig_w, orig_h))
```

---

### C-2 — Entire Class Bodies Duplicated in `widgets.py` ✅

**Location:** `src/widgets.py`

**Problem:** The file contains two complete, separate definitions of both `RegionSelectLabel` and associated `ImageCard` mouse event handlers. In Python, the second definition silently overwrites the first. The first definitions are completely dead but produce the C-1 bug and bloat the file by ~400 lines.

**Fix:** Remove the first `RegionSelectLabel` definition (lines 1093–1166) entirely. Remove all duplicate `mousePressEvent`, `mouseReleaseEvent`, `mouseMoveEvent`, and `show_context_menu` bodies from `ImageCard` (lines 1193–1284).

---

### C-3 — `LoadingDialog.update_timer` Calls `self.parent().active_tool` Without Guard ✅

**Location:** `src/dialogs.py`, `LoadingDialog.update_timer`, lines 934–946

**Problem:**

```python
def update_timer(self):
    if not self.is_downloading:
        elapsed = time.time() - self.start_time
        if self.parent().active_tool == 'bg_remover':
```

The timer runs every 100ms and calls `self.parent().active_tool` unconditionally. If the parent window is garbage-collected or `active_tool` is not yet set, this raises an `AttributeError` silently consumed by the timer callback.

**Fix:**

```python
def update_timer(self):
    if self.is_downloading:
        return
    parent = self.parent()
    if not parent or not hasattr(parent, 'active_tool'):
        return
    elapsed = time.time() - self.start_time
    ...
```

---

## 2. High Severity Issues

### H-1 — Hardcoded Accent Hex Colors Bypass Theme System ✅

**Location:** `src/dialogs.py` — `VectorComparisonDialog` (line 709), `ComparisonDialog` (line 1078), `BatchComparisonDialog` (lines 1233, 1241)

**Problem:** Buttons hardcode `#6366f1` and `#4f46e5` directly, bypassing `tc["accent"]` and `tc["accent_hover"]`.

```python
# Current (wrong)
self.btn_save.setStyleSheet("QPushButton { background-color: #6366f1; }")

# Fix
self.btn_save.setStyleSheet(f"QPushButton {{ background-color: {tc['accent']}; }}")
```

**User Impact:** Custom accent colors and theme changes are ignored on primary action buttons in all AI output dialogs.

---

### H-2 — Confirmation Dialog Button Layouts Violate Design System ✅

**Location:** `src/dialogs.py`, `ConfirmDialog` (line 251), `UpscaleConfirmDialog` (line 393), `VectorConfirmDialog` (line 558)

**Problem:** Buttons are added left-to-right without `addStretch()`, causing them to fill full width rather than being right-anchored. The design system requires: right-aligned, `[Cancel]` left of `[Primary Action]`.

**Fix:** Insert `btn_layout.addStretch()` before `btn_layout.addWidget(self.btn_no)` in all three dialogs.

---

### H-3 — `BatchComparisonDialog` Button Alignment Inverted ✅

**Location:** `src/dialogs.py`, `BatchComparisonDialog`, lines 1243–1248

**Problem:** Destructive ("Discard") and save actions are left-aligned; bulk "Apply to All" actions are right-aligned — the opposite of expected convention. Primary bulk-destructive actions should not sit at the far right without visual weight.

---

### H-4 — `ImageCard` Creates `QGraphicsDropShadowEffect` Twice in `__init__` ✅

**Location:** `src/widgets.py`, `ImageCard.__init__`, lines ~796 and ~900

**Problem:** Two `QGraphicsDropShadowEffect` objects are created and `setGraphicsEffect` is called twice. The first is immediately discarded when the second overwrites it.

**Fix:** Remove the first shadow block (lines ~796–803).

---

### H-5 — `QComboBox` Dropdown Arrow Hidden Globally in All AI Dialogs ✅

**Location:** `src/dialogs.py` — QSS applied in every AI confirmation dialog

**Problem:** `QComboBox::drop-down { border: none; }` removes the native dropdown arrow without a replacement. Combo boxes look like plain text inputs.

**Fix:** Add an explicit arrow or restore the native subcontrol:

```python
"QComboBox::drop-down { border: none; width: 20px; }"
"QComboBox::down-arrow { image: url(:/icons/chevron-down.svg); }"
```

---

### H-6 — `LoadingDialog` Not Closed on All Error Paths in Batch Processing ✅

**Location:** `src/main_window.py`, batch worker callbacks

**Problem:** `on_batch_removal_finished` calls `DetailedErrorDialog.show_error(...)` then `process_next_batch_item()` without closing `loading_dlg` on error. The loading dialog may remain visible behind the error dialog.

---

### H-7 — `CommandPaletteDialog` Uses `FramelessWindowHint` Without Drag Handle ✅

**Location:** `src/command_palette.py`, line 18

**Problem:** Frameless dialog cannot be repositioned by the user. On multi-monitor setups or if it spawns over important content, it is stuck until dismissed.

**Fix:** Implement `mousePressEvent`/`mouseMoveEvent` for drag-repositioning, or add a visible drag handle widget.

---

### H-8 — `RegionSelectLabel` Fixed at 400×360 — Ignores DPI and Parent Size ✅

**Location:** `src/widgets.py`, second `RegionSelectLabel`, lines 1302, 1307–1309

**Problem:** `self.setFixedSize(400, 360)` is set unconditionally. On high-DPI or small screens, this may overflow the parent dialog.

---

## 3. Medium Severity Issues

### M-1 — Mixed QSS Interpolation Patterns in `dialogs.py` ✅

Three incompatible patterns coexist: `.format(**_tc())`, `% _tc()["key"]`, and f-strings with `tc`. Standardize on f-strings with `tc = _tc()` at top of each `__init__`.

---

### M-2 — `SettingsDialog` Places `addStretch()` Between Tab Widget and Buttons ✅

**Location:** `src/dialogs.py`, line 1585

**Problem:** `addStretch()` between the tab widget and the action bar causes buttons to float upward as dialog height grows, violating the "action bar locked to bottom" rule.

**Fix:**

```python
layout.addWidget(self.tab_widget, 1)  # stretch factor
layout.addLayout(btn_layout)          # anchored to bottom, no stretch before it
```

---

### M-3 — Bidirectional Scrollbar Sync Without Loop Guard ✅

**Location:** `src/dialogs.py` — `ComparisonDialog` (lines 1042–1045), `BatchComparisonDialog` (lines 1206–1209), `VectorComparisonDialog` (lines 696–699)

**Problem:** Mutual `valueChanged` → `setValue` connections can trigger feedback loops. Use `blockSignals` in a coordinator:

```python
def _sync_scroll(self, value, target_bar):
    target_bar.blockSignals(True)
    target_bar.setValue(value)
    target_bar.blockSignals(False)
```

---

### M-4 — `LoadingDialog` Minimum Height May Clip Content ✅

**Location:** `src/dialogs.py`, line 888: `self.setMinimumSize(420, 200)`

Long filenames cause the `info` label to wrap to 2–3 lines, clipping at 200px. Increase to 250–280px.

---

### M-5 — `CommandPaletteDialog` Rebuilds Entire List on Every Keystroke ✅

**Location:** `src/command_palette.py`, `filter_items`

`populate_list` clears and recreates all `QWidget` rows on every character. Use `setHidden`/`setVisible` on existing items instead.

---

### M-6 — `tts_tab.py` Runs Side Effects at Import Time ✅

**Location:** `src/tts_tab.py`, lines 40–46

`os.makedirs`, `QSettings` read, and `os.environ["HF_HOME"]` mutation all execute at module import. Move into a lazy init function.

---

### M-7 — `BatchConfirmDialog` Button Bar Not Bottom-Anchored ✅

**Location:** `src/dialogs.py`, `BatchConfirmDialog`, line 323

`addStretch()` before buttons causes the same floating-button issue as M-2.

---

## 4. Low Severity Issues

| ID | Location | Issue |
|---|---|---|
| L-1 | `dialogs.py:79` | `DetailedErrorDialog` "Close" button has `objectName("cancelButton")` — semantic mislabeling ✅ |
| L-2 | `dialogs.py` throughout | `_tc()` called 10–20 times per `__init__`; call once and cache locally |
| L-3 | `dialogs.py:190,198` | `setWindowTitle("Remove Background?")` vs label `"Remove Background"` — inconsistent ✅ |
| L-4 | `widgets.py:1436` | `ZoomPanImagePreview` re-centers only on first resize; subsequent resizes may leave image off-screen ✅ |
| L-5 | `widgets.py:908` | `get_shadow_alpha()` defined but not used in `__init__` shadow color setup ✅ |
| L-6 | `tts_tab.py:190` | `player_manager = AudioPlayerManager()` at module level — `QMediaPlayer` created before `QApplication` is safe ✅ |
| L-7 | `widgets.py:1090` | Mid-file `from PySide6.QtGui import QPen, QColor, QBrush` imports; move to file top ✅ |
| L-8 | `dialogs.py:1461` | `margin-left: 20px` ad-hoc value; design system requires 4px base unit multiples ✅ |
| L-9 | `dialogs.py:1588` | `SettingsDialog` action buttons left-aligned; needs `addStretch()` before cancel ✅ |
| L-10 | `command_palette.py:25` | `border-radius: 0px` is intentional for VS Code-style palette but undocumented; should be commented ✅ |

---

## 5. Styling System Violations

| Location | Violation | Token Expected |
|---|---|---|
| `dialogs.py:709` | `#6366f1` hardcoded | `tc["accent"]` ✅ |
| `dialogs.py:711` | `#4f46e5` hardcoded | `tc["accent_hover"]` ✅ |
| `dialogs.py:1078` | `#6366f1` hardcoded | `tc["accent"]` ✅ |
| `dialogs.py:1080` | `#4f46e5` hardcoded | `tc["accent_hover"]` ✅ |
| `dialogs.py:1233` | `#6366f1` hardcoded | `tc["accent"]` ✅ |
| `dialogs.py:1241` | `#4338ca` hardcoded | No token exists; use `tc["accent"]` ✅ |
| `dialogs.py:858` | `color: #ef4444` in `ImageCard` | `tc["error_color"]` ✅ |
| `widgets.py:1118,1335` | `QColor(99, 102, 241)` for selection region | Should derive from theme accent ✅ |
| `dialogs.py:1461` | `margin-left: 20px` | Design system: 4px base unit only ✅ |
| Multiple combo boxes | `QComboBox` border uses `scrollbar_handle` token | Semantically incorrect; use `border` token ✅ |

---

## 6. Accessibility Issues

| ID | Issue |
|---|---|
| A-1 | `QCheckBox` on `ImageCard` has no text label and no tooltip — unrecognizable to screen readers ✅ |
| A-2 | `ImageCard` has no `setFocusPolicy(Qt.StrongFocus)` — unreachable by keyboard Tab navigation ✅ |
| A-3 | `LoadingDialog` suppresses close button but provides no "this cannot be cancelled" notice ✅ |
| A-4 | No icon-only button tooltips currently, but must be enforced before Bootstrap Icons migration ✅ |

---

## 7. Concurrency Risk ✅

**Main risk:** `self.worker = BGRemovalWorker(...)` in `main_window.py` replaces the worker reference before confirming the prior worker has terminated. If two rapid batch triggers occur, the old `QThread` is garbage-collected while running.

**Fix:** Before creating a new worker: `if self.worker and self.worker.isRunning(): self.worker.wait()`

---

## 8. Code Quality ✅

| ID | Location | Issue |
|---|---|---|
| Q-1 | `widgets.py` | ~400 lines of duplicate class/method bodies to be deleted ✅ |
| Q-2 | `main_window.py:3002` | `CatalogLoader` QThread defined inline inside a method — should be a named class in `workers.py` ✅ |
| Q-3 | `main_window.py` batch callbacks | `print()` used for error logging in packaged application; use `logging` module ✅ |

---

## 9. Prioritized Fix Backlog

### Immediate (Critical/High — Before Release)

| ID | File | Action |
|---|---|---|
| C-1 | `widgets.py` | Fix dead `return self._img_dims` → emit `region_selected` signal ✅ |
| C-2 | `widgets.py` | Delete ~400 lines of duplicate class bodies ✅ |
| C-3 | `dialogs.py` | Guard `update_timer` against unset parent attributes ✅ |
| H-1 | `dialogs.py` | Replace all hardcoded `#6366f1` / `#4f46e5` with theme tokens ✅ |
| H-4 | `widgets.py` | Remove first `QGraphicsDropShadowEffect` block in `ImageCard.__init__` ✅ |
| H-6 | `main_window.py` | Close `loading_dlg` in all batch processing error branches ✅ |

### Short-Term (1–2 Sprints)

| ID | File | Action |
|---|---|---|
| H-2 | `dialogs.py` | Add `addStretch()` before buttons in 3 confirmation dialogs ✅ |
| H-3 | `dialogs.py` | Fix `BatchComparisonDialog` button order per design system ✅ |
| H-5 | `dialogs.py` | Restore visible `QComboBox` dropdown arrow ✅ |
| H-7 | `command_palette.py` | Add drag repositioning to frameless dialog ✅ |
| M-2 | `dialogs.py` | Fix `SettingsDialog` stretch placement ✅ |
| M-3 | `dialogs.py` | Guard bidirectional scrollbar sync with `blockSignals` ✅ |
| M-4 | `dialogs.py` | Increase `LoadingDialog` minimum height ✅ |
| M-5 | `command_palette.py` | Optimize list filtering via visibility toggles ✅ |
| M-6 | `tts_tab.py` | Defer module-level side effects to lazy init ✅ |
| M-7 | `dialogs.py` | Fix `BatchConfirmDialog` button anchoring ✅ |
| L-6 | `tts_tab.py` | Defer `player_manager` instantiation ✅ |
| L-9 | `dialogs.py` | Right-align `SettingsDialog` buttons ✅ |

### Backlog / Polish

| ID | File | Action |
|---|---|---|
| M-1 | `dialogs.py` | Standardize QSS interpolation to f-strings |
| A-1 | `widgets.py` | Add tooltip to `ImageCard` checkbox ✅ |
| A-2 | `widgets.py` | Add focus policy and keyboard handler to `ImageCard` ✅ |
| Q-2 | `main_window.py` | Move `CatalogLoader` to `workers.py` ✅ |
| Q-3 | `main_window.py` | Replace `print()` with `logging` ✅ |
