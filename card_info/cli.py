"""Command line interface for extracting text from images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from .image_text_tool import ImageTextExtractor, OCRConfig, TesseractNotFoundError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text content from images using Tesseract OCR.",
    )
    parser.add_argument("images", nargs="+", type=Path, help="One or more image files to process.")
    parser.add_argument(
        "--lang",
        default="eng",
        help="Language to use for OCR (default: eng).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Additional configuration passed directly to Tesseract.",
    )
    return parser


def run_cli(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    extractor = ImageTextExtractor(OCRConfig(lang=args.lang, config=args.config))

    for image_path in args.images:
        try:
            text = extractor.extract_text(image_path)
        except FileNotFoundError:
            parser.error(f"Image not found: {image_path}")
        except TesseractNotFoundError as exc:  # pragma: no cover - environment dependent
            parser.error(str(exc))
        else:
            header = f"--- {image_path} ---"
            print(header)
            print(text)
            print("-" * len(header))

    return 0


def main() -> None:
    sys.exit(run_cli())


__all__ = ["run_cli", "main", "build_parser"]
