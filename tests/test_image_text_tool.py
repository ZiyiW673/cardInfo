from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from card_info import image_text_tool
from card_info.image_text_tool import (
    ImageTextExtractor,
    OCRConfig,
    TesseractNotFoundError,
    extract_text,
)


@pytest.fixture(autouse=True)
def _skip_tesseract_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_text_tool, "_ensure_tesseract_available", lambda: None)


def _stub_loader(expected_source):
    def loader(source):
        expected_source.append(source)
        return object()

    return loader


def _stub_ocr(result: str, record: dict | None = None):
    record = record if record is not None else {}

    def image_to_string(image, *, lang, config=None):
        record["image"] = image
        record["lang"] = lang
        record["config"] = config
        return result

    return SimpleNamespace(image_to_string=image_to_string)


def test_extract_text_from_path(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake")

    calls: dict = {}
    sources: list = []

    extractor = ImageTextExtractor(
        OCRConfig(lang="eng", config="--psm 6"),
        pytesseract_module=_stub_ocr(" sample text \n", record=calls),
        image_loader=_stub_loader(sources),
    )

    text = extractor.extract_text(image_path, check_tesseract=False)

    assert text == "sample text"
    assert calls["lang"] == "eng"
    assert calls["config"] == "--psm 6"
    assert sources == [image_path]


def test_extract_text_from_bytes(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake")
    data = image_path.read_bytes()

    sources: list = []

    text = extract_text(
        data,
        lang="eng",
        check_tesseract=False,
        pytesseract_module=_stub_ocr("Hello"),
        image_loader=_stub_loader(sources),
    )

    assert text == "Hello"
    assert isinstance(sources[0], bytes)


def test_missing_tesseract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake")

    def raise_missing():
        raise TesseractNotFoundError("missing")

    monkeypatch.setattr(image_text_tool, "_ensure_tesseract_available", raise_missing)

    with pytest.raises(TesseractNotFoundError):
        extract_text(
            image_path,
            check_tesseract=True,
            pytesseract_module=_stub_ocr(""),
            image_loader=_stub_loader([]),
        )


def test_cli_outputs_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake")

    # Stub the extractor so the CLI returns predictable output without invoking OCR.
    extractor = SimpleNamespace(extract_text=lambda _path, check_tesseract=True: "hi")

    def fake_extractor(config=None, *, pytesseract_module=None, image_loader=None):
        return extractor

    original_extractor = image_text_tool.ImageTextExtractor
    image_text_tool.ImageTextExtractor = fake_extractor  # type: ignore[assignment]

    from card_info.cli import run_cli

    try:
        code = run_cli([str(image_path)])
    finally:
        image_text_tool.ImageTextExtractor = original_extractor  # type: ignore[assignment]

    captured = capsys.readouterr()

    assert code == 0
    assert "---" in captured.out
    assert "hi" in captured.out
