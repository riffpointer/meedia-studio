# Meedia Studio - Future Tool Expansion Ideas

This document outlines new tool ideas and feature expansions for **Meedia Studio**. These tools leverage local deep learning models (ONNX, OpenCV) and python-based media processing to keep the application lightweight, fast, and feature-rich.

---

## 1. AI Object Eraser & Inpainter (Smart Erase)
* **Description**: Allows the user to brush over an unwanted object in an image and automatically fills in the background realistically using AI.
* **How it works**: 
  * Uses a brush canvas overlay.
  * Runs a lightweight Inpainting model (such as **LaMa** or **AOT-GAN**) converted to ONNX format.
  * Processes the masked area locally to reconstruct the background seamlessly.

## 2. Text & Watermark Remover
* **Description**: Automatically detects and removes text, timestamps, or watermark overlays from images and emojis.
* **How it works**:
  * Uses **CRAFT** (Character Region Awareness for Text Detection) in ONNX to find text bounding boxes.
  * Feeds the text regions into an inpainting pipeline to automatically clean the image.

## 3. Raster to Vector converter (SVG Vectorizer) [Completed]
* **Description**: Converts raster emojis (PNG, JPG) into high-quality scalable vector graphics (SVG) so they can be resized infinitely without losing quality.
* **How it works**:
  * Runs a custom tracing pipeline using OpenCV (`cv2.findContours`, `cv2.approxPolyDP`).
  * Supports **Color mode** using K-Means color quantization (2 to 16 colors) and **Monochrome mode** using gray or alpha channel thresholding.
  * Uses `evenodd` SVG fill-rule to handle complex nested shapes and holes natively, and outputs clean SVG files.

## 4. Smart Image Compressor & Format Converter
* **Description**: A batch processing tool to convert between formats (WebP, PNG, JPG, BMP) and optimize file size using quality sliders and metadata stripping.
* **How it works**:
  * Leverages PIL (`Pillow`) parameters to adjust quality, optimize Huffman tables, and strip EXIF metadata.
  * Allows converting images to **WebP** format for maximum web efficiency.

## 5. Duplicate & Similar Image Cleaner
* **Description**: Scans the active folder, detects identical or near-identical images (such as similar emojis or duplicate downloads), and suggests which ones to clean up.
* **How it works**:
  * Computes perceptual hashes (**dHash** or **pHash**) for all loaded images.
  * Calculates Hamming distance between hashes.
  * Groups similar files in the UI and provides a checkbox list to delete duplicates.

## 6. AI Colorizer (Black & White to Color)
* **Description**: Restores or adds color to grayscale photos or drawings using a deep learning colorization model.
* **How it works**:
  * Uses a pre-trained colorization model (like **DeOldify** or **ECCV16/SIGGRAPH17** colorizers) loaded via OpenCV's `dnn` module.
  * Maps the Lightness channel (L) of the Lab color space and predicts the A & B chromaticity channels.

## 7. Video to GIF/WebP Animation Converter
* **Description**: Allows converting short video clips into high-quality animated GIFs or WebP files with options for frame rate, scale, and color dithering.
* **How it works**:
  * Uses `imageio` or a Python wrapper around `ffmpeg`.
  * Optimizes color palettes per frame to avoid color banding in standard GIFs.

## 8. Pixel Art Upscaler & Sharp Edge Preserver
* **Description**: A specialized upscaler for retro/pixel art emojis that preserves sharp, crisp pixel edges without blurring or anti-aliasing.
* **How it works**:
  * Integrates **xBRZ** or **hq4x** interpolation algorithms.
  * Optionally allows grid-alignment correction to clean up hand-drawn pixel shapes.

## 9. Color Palette Swapper & Theme Generator
* **Description**: Extracts color palettes from existing emojis and lets the user swap specific colors or apply predefined themes (e.g., Cyberpunk, Pastel, Monochrome) across cards.
* **How it works**:
  * Extracts dominant colors using color quantization.
  * Allows mapping color keys to new hex colors and rebuilding the image dynamically.

## 10. AI Image-to-Emoji Creator (Lightweight Diffusion)
* **Description**: Generates entirely custom transparent emojis directly from text prompts using a local or API-driven diffusion model.
* **How it works**:
  * Leverages lightweight local Stable Diffusion models (via ONNX runtime) or cloud API integrations.
  * Automatically applies background removal to ensure transparency.

## 11. Smart Crop & Auto-Reframe
* **Description**: Automatically detects the most important subject in an image and crops/reframes it to common aspect ratios (1:1, 16:9, 4:3) without cutting off the subject.
* **How it works**:
  * Uses a saliency detection model (ONNX) to find the focal point of the image.
  * Calculates the optimal crop window centered on the subject and resizes accordingly.

## 12. Noise Reduction & Image Deblur
* **Description**: Removes grain, JPEG artifacts, or motion blur from low-quality images using AI-powered restoration.
* **How it works**:
  * Runs a lightweight denoising/deblurring model (e.g., **DnCNN** or **MPRNet** converted to ONNX).
  * Applies to the full image or a user-selected region only.

## 13. Sprite Sheet Slicer & Packer
* **Description**: Splits a single sprite sheet image into individual frames, or packs a folder of images into an optimized sprite sheet with auto-generated CSS/JSON coordinates.
* **How it works**:
  * Detects individual frames via uniform grid slicing or white-space gap detection with OpenCV.
  * Packs images using a bin-packing algorithm and exports coordinates as a JSON/CSS file.

## 14. Favicon & App Icon Generator
* **Description**: Takes any image and generates a complete set of platform-ready icons — browser favicons (`favicon.ico`, `favicon.png`), Android launcher icons, and Apple touch icons — in one click.
* **How it works**:
  * Uses Pillow to resize and center-crop the source image to every required size (16×16 up to 1024×1024).
  * Assembles a `.ico` file with multiple embedded sizes and exports a ZIP archive.

## 15. Emoji Grid / Sheet Builder
* **Description**: Lets the user select multiple image cards and arrange them into a custom grid or sticker sheet, then exports the composite as a single PNG.
* **How it works**:
  * Displays a drag-and-reorder grid preview in a dialog.
  * Uses Pillow's `Image.paste()` to composite all selected images onto a canvas with configurable padding and background color.

## 16. Batch Rename & Metadata Tagger
* **Description**: Renames a batch of loaded images with a custom pattern (e.g., `emoji_{n:03d}`) and optionally embeds EXIF/XMP metadata tags (author, description, keywords).
* **How it works**:
  * Applies user-defined naming templates with sequence numbers, dates, or source filename fragments.
  * Uses Pillow's `PngInfo` or `piexif` to write metadata without re-encoding the image.

## 17. Color Picker & Palette Exporter
* **Description**: A click-to-sample color picker that lets users click anywhere on a loaded image to extract its color, build a palette, and export it as CSS variables, JSON, or a `.ase` Adobe Swatch file.
* **How it works**:
  * Captures click coordinates on the preview label and reads the pixel RGBA from the loaded PIL image.
  * Accumulates swatches in a panel and serializes them on export.

## 18. Transparent Background Color Fill
* **Description**: Replaces the transparency in a PNG with a solid color or gradient fill (e.g., add a white, black, or custom background before sharing on platforms that do not support alpha).
* **How it works**:
  * Creates a new Pillow canvas in the target color and composites the original PNG on top using `Image.alpha_composite`.

## 19. Image Metadata Viewer & Stripper
* **Description**: Displays all embedded metadata (EXIF, ICC profile, GPS coordinates, copyright, camera settings) in a structured panel, and offers a one-click option to strip it all for privacy.
* **How it works**:
  * Reads EXIF via `piexif` and ICC/XMP via Pillow's `info` dict.
  * Stripping re-saves the image through Pillow without passing the metadata dictionaries.

## 20. Side-by-Side Before/After Comparison Export
* **Description**: Generates a shareable before/after comparison image that shows the original and processed result side-by-side (or with a split-slider preview) with an optional label banner.
* **How it works**:
  * Composites both images onto a new Pillow canvas with a configurable divider line and optional text labels.
  * Exports as a single PNG or animated WebP that transitions between states.

---

## UX Improvements

These are quick-to-implement quality-of-life improvements that significantly reduce friction in daily use.

### 1. Remember Last-Used Output Directory
**Problem**: Every time the user exports or saves, they have to navigate to the same folder manually.
**Fix**: Persist the last-used output directory in `settings.json` and pre-populate it as the default path in every `QFileDialog`.

### 2. Drag-and-Drop Images Directly from File Explorer
**Problem**: Users must click "Add Images" and navigate the file picker every time.
**Fix**: Enable `setAcceptDrops(True)` on the main scroll area and implement `dropEvent` to accept dragged `.png`, `.jpg`, `.webp`, `.svg` files directly from Windows Explorer.

### 3. Keyboard Shortcuts for Common Actions
**Problem**: Every action requires mouse clicks through the UI — repetitive and slow.
**Fix**: Bind `Ctrl+O` (open images), `Ctrl+A` (select all cards), `Delete` (remove selected), `Ctrl+Z` (undo last removal), and `Ctrl+S` (save/export selection) using `QShortcut`.

### 4. Select All / Deselect All Checkbox in Batch Dialogs
**Problem**: When processing 30+ images in batch mode, users must tick every checkbox individually.
**Fix**: Add a "Select All / None" master checkbox at the top of every batch confirmation dialog that toggles all items at once.

### 5. Undo Last Remove / Process Action
**Problem**: Accidentally removing a card or overwriting a file has no recovery path.
**Fix**: Keep a small in-memory stack (last 5 operations) that stores the removed card's file path and metadata so the user can hit `Ctrl+Z` to restore it.

### 6. Inline Progress on Each Card During Batch Processing
**Problem**: During batch operations, only a single global progress bar exists — the user cannot tell which specific card is being processed.
**Fix**: Show a small animated progress ring or shimmer overlay directly on each `ImageCard` widget while it is being processed, clearing it on completion.

### 7. Toast Notifications Instead of Modal Dialogs for Success Messages
**Problem**: Success message boxes (`QMessageBox`) require the user to click "OK" and interrupt workflow.
**Fix**: Replace success pop-ups with non-blocking slide-in toast notifications at the bottom-right of the window that auto-dismiss after 3 seconds.

### 8. Right-Click Context Menu on Image Cards
**Problem**: Most card actions are buried in toolbars or require switching the active tool tab first.
**Fix**: Implement a `QMenu` on right-click of any `ImageCard` offering: _Open in Explorer_, _Copy to Clipboard_, _Rename_, _Remove from List_, and _Process with current tool_.

### 9. Copy-to-Clipboard Button on Every Card
**Problem**: Sharing a processed image requires opening it in Explorer, then manually copying — multiple steps.
**Fix**: Add a small clipboard icon button overlay on each card. Clicking it copies the image data to `QClipboard` in both PNG and file-path formats so it can be pasted into any app or chat.

### 10. Persistent Window Size & Position
**Problem**: Every session starts with the default 950×750 window in the top-left corner.
**Fix**: On close, write `window_geometry` to `settings.json` using `saveGeometry()`. On open, restore it with `restoreGeometry()` so the app remembers where and how large the user left it.

### 11. Search / Filter Bar for Loaded Images
**Problem**: When 100+ images are loaded, finding a specific file requires scrolling through the whole grid.
**Fix**: Add a search input at the top of the image grid that filters visible cards in real-time by filename substring match.

### 12. Sort Cards by Name, Size, or Date
**Problem**: Images appear in the order they were added, making it impossible to find files quickly.
**Fix**: Add a sort dropdown ("Name ↑", "Name ↓", "File Size", "Date Modified") that re-orders the card grid without reloading images.

### 13. Show File Size and Dimensions on Card Hover
**Problem**: Users have no quick way to check an image's resolution or size without opening it externally.
**Fix**: On mouse hover, display a small tooltip or overlay badge on the card showing `WxH px · X KB` read from the image metadata.

### 14. Multi-Select Cards with Shift+Click & Ctrl+Click
**Problem**: Selecting a range of cards for batch actions requires clicking each one individually.
**Fix**: Implement standard Shift+Click (range select) and Ctrl+Click (toggle individual) selection on `ImageCard` widgets, highlighting selected cards with a colored border.

### 15. Auto-Skip Already-Processed Files in Batch
**Problem**: Re-running a batch on a folder re-processes files that already have output, wasting time.
**Fix**: Before processing, check if an output file with the same name already exists in the output directory and offer to skip those files, only processing new ones.

### 16. Collapsible Tool Settings Panel
**Problem**: The settings/options area (model picker, sliders, etc.) takes up vertical space even when the user has already configured their preferred defaults.
**Fix**: Wrap the tool configuration panel in a collapsible section with an arrow toggle button so power users can hide it and maximize the image grid area.

### 17. Recent Files / Recent Folders Quick Access
**Problem**: Re-opening the same project folder requires navigating the file picker from scratch each time.
**Fix**: Maintain a "Recent Folders" list (last 5) in `settings.json` and expose it as a dropdown next to the "Add Images" button for one-click re-access.

### 18. Confirm Before Overwriting Output Files
**Problem**: Re-exporting silently overwrites existing output files with no warning.
**Fix**: Before writing any output file, check if it exists and show a lightweight inline prompt ("Overwrite existing file?") instead of silently replacing it.

### 19. Status Bar with Live Card Count & Selection Info
**Problem**: There is no at-a-glance summary of the current session (how many images are loaded, how many are selected, total size).
**Fix**: Add a `QStatusBar` at the bottom of the main window displaying: `{N} images loaded · {M} selected · {total_size} MB`.

### 20. Dark/Light Mode Toggle
**Problem**: The app is hard-coded to a dark theme — users in bright environments may find it uncomfortable.
**Fix**: Add a mode toggle button (sun/moon icon) in the toolbar that swaps between the current dark palette and a clean light palette by re-applying a stylesheet, persisting the preference in `settings.json`.
