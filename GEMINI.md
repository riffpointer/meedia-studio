# Meedia Studio — System Instructions & Constraints

## 1. Project Context & Stack
- App Type: Desktop creator toolkit (BG remover, upscale, vectorizer, yt-dlp frontend, etc.).
- Core Stack: Python 3, PySide6 (Qt for Python), ONNX Runtime, and hardware-accelerated AI models.
- Core Values: Pixel-perfect UI/UX, flawless asynchronous thread handling, and absolute token economy.

## 2. Python & PySide6 Development Instructions
- Architecture: Always separate UI layout from processing logic. Use PySide6 Signals and Slots for inter-component communication.
- Concurrency: Never run AI inference, file I/O, or heavy processing (like yt-dlp or ONNX execution) on the main GUI thread. Always implement `QThread` or `QRunnable` with `QThreadPool` to prevent UI freezing.
- Resource Management: Explicitly release memory/GPU assets when closing tools or switching views (e.g., clearing ONNX inference sessions).

## 3. UI/UX Design Constraints & Layout Engine Defenses
- Component Styling: The app has a strict UX design principle. Use it consistently; do not invent new styles. Use explicit layouts, appropriate padding, and accessible contrast ratios.
- Responsive Behavior & Scaling Protection: High-DPI scaling must be supported. Define explicit minimum, maximum, or fixed sizes for windows, dialogs, and modular tool panes.
- Strict Dialog Layout Rules (Anti-Stretch): 
    - Never allow layouts to behave like `justify-content: space-around`. If a dialog window expands in height, elements must not awkwardly stretch or scatter across the canvas.
    - Always anchor components tightly to the top or sides using explicit `addStretch()` / `QSpacerItem` calls at the bottom of the layout layout chain to push empty space downward.
- Visual Layout Stability (Anti-Shifting):
    - Background tasks, toggle panes, or progress bars must never cause structural layout shifts or jumpy UIs when toggled.
    - Persistent action bars (e.g., bottom Cancel/OK buttons) must remain strictly locked to the bottom boundary of the dialog.
    - Use `QStackedLayout` or enforce rigid `minimumSize` / fixed dimensions on dynamic elements (like progress bars) so that their appearance or absence does not alter the geometry or positions of adjacent controls.
- Feedback Loops: Provide immediate visual feedback for all background processes (e.g., granular progress bars, micro-animations, or dynamic status text).

## 4. Antigravity Agent Rules & Token Economy
- Strict Output Format: Do not provide conversational filler, pleasantries, or post-fix explanations.
- Code Delivery: Output strict, localized micro-diffs or exact function replacements. Do not rewrite full files or unedited boilerplate.
- Verification Guardrail: After completing a coding task, do not run any python compile checks. Output the exact string: "Done."

# Meedia Studio — UI/UX Design System & Constraints

## 1. Visual Tokens (Strict)
- **Corner Radii:** Buttons, cards, dialogs = 8px. Inputs, checkboxes, combo-boxes, tags = 4px. No pills.
- **Colors (Tri-Color Stack):** - `Primary`: CTAs, active states, progress fills.
  - `Secondary`: Secondary actions, toggle-off, subtle highlights.
  - `Tertiary`: Backgrounds, dividers, disabled states, low-emphasis text.
  - *No ad-hoc hex/RGB values allowed.*
- **Typography:** System font (Segoe UI on Windows). Max 3 sizes: Title (16px, Semibold), Body (13px, Regular), Caption (11px, Regular). Semibold for headings/primary actions. No all-caps > 2 words.
- **Iconography:** Monochrome. Sizes: Inline = 16×16, Toolbar = 20×20, Actions = 24×24. Tooltips mandatory on icon-only buttons.
- **Spacing:** Base unit = 4px. Layout padding = 16px. Sibling gap = 8px. Section gap = 16px. Min click target = 32×32px.

## 2. Core UX Principles
- **Hierarchy:** Exactly ONE primary action (filled/accented) per view. Secondary is outlined/flat. Destructive is red text/outlined (never filled red in normal flow).
- **Feedback:** UI reaction < 100ms. If longer, show spinner/progress bar, disable trigger control, and run async. No modal success dialogs (use toasts).
- **Placement:** Fields top-to-bottom. Bottom action bar: Right-aligned, `[Cancel]` always to the LEFT of `[Primary Action]`. Use verb-style labels ("Save", "Apply"), not "OK".
- **Safety:** Destructive actions require confirmation naming the target ("Delete 3 images?"). Focus rings must always be visible. Tab navigation must work.

## 3. Mandatory Component Patterns
- **Cards:** Fixed aspect ratio or fixed height per row. Hover = subtle shadow increase. Selection = accented border/checkmark (never fill background).
- **Dialogs:** Title = concise noun phrase. Max width = 480px (unless previewing). Always closable via `Escape`.
- **Tab Bars:** Single line only (no wrapping). Active tab = 2px primary bottom border. No icons-only tabs.
- **Toolbars:** Max 7±2 actions, rest overflow into "⋯". Located at the top of context.
- **Scroll Areas:** Visible scrollbar on hover. Empty states must show centered placeholder text/icon.
- **Forms:** Labels above or left of controls. Real-time validation on focus-lost. Disable "Save" until form is dirty.

## 4. Pre-Flight Layout Validation Checklist (Execute Mentally Before Output)
- [ ] **Overflow:** No text truncation/clipping at minimum window size. (Use QLabel word-wrap or elide).
- [ ] **Alignment:** Multiples of 4px. Text baselines aligned. Action buttons right-aligned.
- [ ] **Spacing:** No 0px gaps. Layout margins explicitly set (never rely on defaults).
- [ ] **Hierarchy:** Eye lands on the single primary CTA first.
- [ ] **Empty State:** Centered placeholder text/icon present for all empty lists/grids/scroll areas.
- [ ] **Redundancy:** Flattened container nesting, no decorative-only wrappers.
- [ ] **Interaction:** Every control has distinct hover/pressed/disabled states. Tab/Enter/Escape work.
- [ ] **Superiority:** Choose the absolute simplest layout. Fewer containers and moving parts = always better.