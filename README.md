# Meedia Studio

Meedia Studio is a desktop application that helps you remove backgrounds from images. It uses artificial intelligence (AI) to find the main object in an image and make the background transparent.

## Features

* Remove backgrounds from images using AI.
* Choose from different AI models for the best results.
* Zoom in and out to compare the original and processed images side by side.
* Support for upscaling images to make them larger and clearer.

## Project Structure

The code is split into several smaller files in the `src` folder for better management:

* `main.py` - The main file that starts the application.
* `src/config.py` - Settings and model details used by the app.
* `src/utils.py` - Simple helper functions for images, files, and vectorizing.
* `src/workers.py` - Background tasks that run the AI models without freezing the screen.
* `src/widgets.py` - Custom visual elements like the tab bar and image cards.
* `src/dialogs.py` - Pop-up windows for settings, previews, and confirmations.
* `src/main_window.py` - The main layout and logic of the application screen.

## Requirements

Before running the application, make sure you have Python installed on your computer.

The application also requires the following Python libraries:
* PySide6 (for the user interface)
* rembg (for background removal)
* pillow (for image processing)

You can install all required libraries by running this command in your terminal:

```bash
pip install -r requirements.txt
```

## How to Run

To start the application, run this command in your terminal:

```bash
python main.py
```

## How to Use

1. Open the application.
2. Click the button to select and load an image.
3. Select the AI model you want to use from the settings menu.
4. Click the process button to remove the background.
5. Save your new image with a transparent background.
