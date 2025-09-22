"""Web interface for extracting text from images."""

from __future__ import annotations

import argparse
import html
import io
from email.parser import BytesParser
from email.policy import default as email_default_policy
from string import Template
from typing import Protocol
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from .image_text_tool import OCRDependencyError, TesseractNotFoundError, extract_text


class ExtractTextCallable(Protocol):
    """Callable interface matching :func:`card_info.extract_text`."""

    def __call__(
        self,
        image_source,
        *,
        lang: str = "eng",
        config: str | None = None,
        check_tesseract: bool = True,
    ) -> str:
        ...


_HTML_TEMPLATE = Template(
    """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Image Text Extractor</title>
    <style>
      :root {
        color-scheme: light dark;
        font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      }
      body {
        margin: 0;
        background: #f4f4f4;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1.5rem;
      }
      .panel {
        max-width: 720px;
        width: 100%;
        background: white;
        border-radius: 12px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
        padding: 2rem;
      }
      h1 {
        margin-top: 0;
        text-align: center;
      }
      form {
        display: grid;
        gap: 1rem;
      }
      label {
        font-weight: 600;
        display: block;
        margin-bottom: 0.25rem;
      }
      input[type="text"], input[type="file"], textarea {
        width: 100%;
        padding: 0.75rem;
        border-radius: 8px;
        border: 1px solid #ccd1d9;
        font: inherit;
      }
      button {
        border: none;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        background: #1a73e8;
        color: white;
        font-weight: 600;
        cursor: pointer;
      }
      button:hover {
        background: #1558b0;
      }
      .result {
        margin-top: 1.5rem;
      }
      .error {
        background: #fdecea;
        color: #a4282d;
        border: 1px solid #f5c6cb;
        padding: 0.75rem;
        border-radius: 8px;
      }
    </style>
  </head>
  <body>
    <main class="panel">
      <h1>Image Text Extractor</h1>
      <form method="post" enctype="multipart/form-data">
        <div>
          <label for="image">Upload image</label>
          <input id="image" name="image" type="file" accept="image/*" required>
        </div>
        <div>
          <label for="lang">Language (Tesseract code)</label>
          <input id="lang" name="lang" type="text" value="${lang}" placeholder="eng">
        </div>
        <div>
          <label for="config">Additional Tesseract config</label>
          <input id="config" name="config" type="text" value="${config}" placeholder="--psm 6">
        </div>
        <div>
          <button type="submit">Extract text</button>
        </div>
      </form>
      ${error_block}
      ${result_block}
    </main>
  </body>
</html>
"""
)


def _render_page(lang: str, config_value: str, text: str | None, error: str | None) -> str:
    safe_lang = html.escape(lang or "eng", quote=True)
    safe_config = html.escape(config_value or "", quote=True)

    error_block = ""
    if error:
        error_block = f'<div class="error" role="alert">{html.escape(error)}</div>'

    result_block = ""
    if text is not None:
        escaped_text = html.escape(text)
        result_block = (
            '<section class="result">'
            "<h2>Extracted text</h2>"
            f'<textarea rows="12" readonly>{escaped_text}</textarea>'
            "</section>"
        )

    return _HTML_TEMPLATE.substitute(
        lang=safe_lang,
        config=safe_config,
        error_block=error_block,
        result_block=result_block,
    )


def _parse_multipart_form(environ: dict) -> tuple[dict[str, str], dict[str, io.BytesIO]]:
    content_type = environ.get("CONTENT_TYPE", "")
    if "multipart/form-data" not in content_type:
        return {}, {}

    length = environ.get("CONTENT_LENGTH")
    try:
        content_length = int(length) if length else None
    except ValueError:
        content_length = None

    wsgi_input = environ.get("wsgi.input")
    if wsgi_input is None:
        return {}, {}

    body = wsgi_input.read(content_length) if content_length is not None else wsgi_input.read()
    message = BytesParser(policy=email_default_policy).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
    )

    fields: dict[str, str] = {}
    files: dict[str, io.BytesIO] = {}

    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        name = part.get_param("name", header="Content-Disposition")
        if not name:
            continue

        filename = part.get_filename()
        if filename:
            data = part.get_payload(decode=True) or b""
            files[name] = io.BytesIO(data)
            continue

        value = part.get_content()
        if isinstance(value, bytes):
            charset = part.get_content_charset() or "utf-8"
            value = value.decode(charset, errors="ignore")
        fields[name] = value

    environ["wsgi.input"] = io.BytesIO(body)
    return fields, files


def create_app(extract_text_func: ExtractTextCallable | None = None):
    """Create a WSGI application exposing the OCR tool via the web."""

    extractor = extract_text_func or extract_text

    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        text: str | None = None
        error: str | None = None

        if method == "POST":
            fields, files = _parse_multipart_form(environ)
            lang = fields.get("lang", "eng") or "eng"
            config_value = fields.get("config", "") or ""
            upload = files.get("image")

            if upload is None:
                error = "Please choose an image file to upload."
            else:
                upload.seek(0)
                try:
                    text = extractor(upload, lang=lang, config=config_value or None)
                except (TesseractNotFoundError, OCRDependencyError) as exc:
                    error = str(exc)
                    text = None
                except Exception as exc:  # pragma: no cover - defensive fallback
                    error = f"Failed to extract text: {exc}"
                    text = None
            body = _render_page(lang, config_value, text, error)
        else:
            query = parse_qs(environ.get("QUERY_STRING", ""))
            lang = query.get("lang", ["eng"])[0] or "eng"
            config_value = query.get("config", [""])[0] or ""
            body = _render_page(lang, config_value, None, None)

        data = body.encode("utf-8")
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(data))),
        ]
        start_response("200 OK", headers)
        return [data]

    return app


def main(argv: list[str] | None = None) -> None:
    """Run the development web server."""

    parser = argparse.ArgumentParser(description="Run the card-info web interface.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    args = parser.parse_args(argv)

    app = create_app()
    with make_server(args.host, args.port, app) as server:
        print(f"Serving card-info web UI on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover - manual shutdown
            print("\nShutting down web server...")


if __name__ == "__main__":  # pragma: no cover - manual execution convenience
    main()


__all__ = ["create_app", "main"]
