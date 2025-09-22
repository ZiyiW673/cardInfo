from __future__ import annotations

import io
from typing import Callable
from wsgiref.util import setup_testing_defaults

import pytest

from card_info.web import create_app


class StubExtractor:
    def __init__(self, response: str = "stub text") -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        image_source,
        *,
        lang: str = "eng",
        config: str | None = None,
        check_tesseract: bool = True,
    ) -> str:
        data = image_source.read()
        if hasattr(image_source, "seek"):
            image_source.seek(0)
        self.calls.append({"lang": lang, "config": config, "data": data})
        return self.response


@pytest.fixture()
def wsgi_app() -> tuple[Callable, StubExtractor]:
    stub = StubExtractor()
    return create_app(extract_text_func=stub), stub


def call_app(app: Callable, environ: dict) -> tuple[str, list[tuple[str, str]], bytes]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


def make_environ(method: str = "GET", body: bytes = b"", content_type: str | None = None) -> dict:
    environ: dict = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["wsgi.input"] = io.BytesIO(body)
    environ["CONTENT_LENGTH"] = str(len(body))
    if content_type:
        environ["CONTENT_TYPE"] = content_type
    return environ


def encode_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----CardInfoBoundary"
    buffer = io.BytesIO()

    for name, value in fields.items():
        buffer.write(f"--{boundary}\r\n".encode())
        buffer.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buffer.write(value.encode())
        buffer.write(b"\r\n")

    for name, (filename, data, content_type) in files.items():
        buffer.write(f"--{boundary}\r\n".encode())
        buffer.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode())
        buffer.write(data)
        buffer.write(b"\r\n")

    buffer.write(f"--{boundary}--\r\n".encode())
    return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"


def test_index_renders_form(wsgi_app):
    app, _ = wsgi_app
    status, headers, body = call_app(app, make_environ())

    assert status.startswith("200")
    assert b"Image Text Extractor" in body
    assert ("Content-Type", "text/html; charset=utf-8") in headers


def test_extract_text_success():
    stub = StubExtractor(response="hello world")
    app = create_app(extract_text_func=stub)

    body, content_type = encode_multipart(
        {"lang": "deu", "config": "--psm 6"},
        {"image": ("sample.png", b"fake image", "image/png")},
    )
    status, _, response_body = call_app(app, make_environ("POST", body, content_type))

    assert status.startswith("200")
    assert b"hello world" in response_body
    assert stub.calls
    assert stub.calls[0]["lang"] == "deu"
    assert stub.calls[0]["config"] == "--psm 6"


def test_missing_image_shows_error(wsgi_app):
    app, stub = wsgi_app

    body, content_type = encode_multipart({"lang": "eng"}, {})
    status, _, response_body = call_app(app, make_environ("POST", body, content_type))

    assert status.startswith("200")
    assert b"Please choose an image file to upload." in response_body
    assert stub.calls == []
