# cardInfo

Utilities for extracting textual information from image files. The project
provides a small Python module and command line interface that wraps the
Tesseract OCR engine via [pytesseract](https://pypi.org/project/pytesseract/).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Ensure the [Tesseract OCR](https://tesseract-ocr.github.io/) binary is
installed and available on your system `PATH`. On Debian/Ubuntu based systems
it can typically be installed with `sudo apt-get install tesseract-ocr`.

## Usage

### Python API

```python
from card_info import extract_text

text = extract_text("example.png")
print(text)
```

### Command Line Interface

```bash
card-info path/to/image.png
```

The CLI prints the recognised text for each provided image. Use `--lang` to
change the OCR language and `--config` to pass advanced options directly to
Tesseract.

## Running Tests

```bash
pytest
```

Tests mock out the OCR engine so they can run without the Tesseract binary.
