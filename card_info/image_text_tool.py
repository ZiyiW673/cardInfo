"""Extract text from images using OCR engines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
import importlib
import io
import shutil


class OCRDependencyError(RuntimeError):
    """Raised when a required dependency for OCR is missing."""


class TesseractNotFoundError(RuntimeError):
    """Raised when the Tesseract binary cannot be located."""


@dataclass(slots=True)
class OCRConfig:
    """Configuration for OCR extraction."""

    lang: str = "eng"
    config: str | None = None


class ImageLoader(Protocol):
    """Protocol describing a callable that loads images."""

    def __call__(self, source: str | Path | bytes | BinaryIO):
        ...


class PytesseractModule(Protocol):
    """Subset of :mod:`pytesseract` used by this module."""

    def image_to_string(self, image, lang: str = ..., config: str | None = ...):
        ...


class ImageTextExtractor:
    """Helper class for extracting text from images."""

    def __init__(
        self,
        ocr_config: OCRConfig | None = None,
        *,
        pytesseract_module: PytesseractModule | None = None,
        image_loader: ImageLoader | None = None,
    ) -> None:
        self.ocr_config = ocr_config or OCRConfig()
        self._pytesseract = pytesseract_module or _import_pytesseract()
        self._load_image = image_loader or _default_image_loader

    def extract_text(
        self,
        image_source: str | Path | bytes | BinaryIO,
        *,
        check_tesseract: bool = True,
    ) -> str:
        """Extract text from the provided image source."""

        if check_tesseract:
            _ensure_tesseract_available()

        image = self._load_image(image_source)
        text = self._pytesseract.image_to_string(
            image,
            lang=self.ocr_config.lang,
            config=self.ocr_config.config,
        )
        return text.strip()


def extract_text(
    image_source: str | Path | bytes | BinaryIO,
    *,
    lang: str = "eng",
    config: str | None = None,
    check_tesseract: bool = True,
    pytesseract_module: PytesseractModule | None = None,
    image_loader: ImageLoader | None = None,
) -> str:
    """Convenience wrapper around :class:`ImageTextExtractor`."""

    extractor = ImageTextExtractor(
        OCRConfig(lang=lang, config=config),
        pytesseract_module=pytesseract_module,
        image_loader=image_loader,
    )
    return extractor.extract_text(image_source, check_tesseract=check_tesseract)


def _import_pytesseract() -> PytesseractModule:
    try:
        return importlib.import_module("pytesseract")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
        raise OCRDependencyError(
            "pytesseract is required to extract text. Install it with 'pip install pytesseract'."
        ) from exc


def _default_image_loader(source: str | Path | bytes | BinaryIO):
    image_module = _import_pillow_image_module()

    if isinstance(source, (str, Path)):
        return image_module.open(source)

    if isinstance(source, bytes):
        stream: BinaryIO = io.BytesIO(source)
        return image_module.open(stream)

    if hasattr(source, "read"):
        return image_module.open(source)

    raise TypeError(
        "Unsupported image source type. Expected path, bytes, or binary file-like object."
    )


def _import_pillow_image_module():
    try:
        return importlib.import_module("PIL.Image")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
        raise OCRDependencyError(
            "Pillow is required to load images. Install it with 'pip install pillow'."
        ) from exc


def _ensure_tesseract_available() -> None:
    if shutil.which("tesseract") is None:
        raise TesseractNotFoundError(
            "Tesseract OCR engine is required but was not found in PATH. "
            "Install it from https://github.com/tesseract-ocr/tesseract or "
            "use the system package manager and ensure the 'tesseract' binary is accessible."
        )


__all__ = [
    "ImageTextExtractor",
    "OCRConfig",
    "extract_text",
    "TesseractNotFoundError",
    "OCRDependencyError",
]
