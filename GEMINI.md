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