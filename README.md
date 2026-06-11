# Meedia Studio

Meedia Studio is a desktop application that helps you remove backgrounds from images. It uses artificial intelligence (AI) to find the main object in an image and make the background transparent.

## Features

* Remove backgrounds from images using AI.
* Choose from different AI models for the best results.
* Zoom in and out to compare the original and processed images side by side.
* Support for upscaling images to make them larger and clearer.

## Requirements

This program utilizes some local AI tools. You don't need a super computer to run most of the tools in this app, but it's recommended to have an RTX or an RX XT series GPU. Tool compatibility varies according to the GPU, so if something does not work well on your GPU setup, please let us know by opening an issue! This app has been tested on Nvidia RTX 5060.

Before running the application, make sure you have Python installed on your computer.

Install all required libraries by running this command:
```bash
pip install -r requirements.txt
```

## How to Run

To start the application, run this command:
```bash
python main.py
```

## License
Licensed under the Mozilla Public License Version 2.0. For more info, read [LICENSE](LICENSE).