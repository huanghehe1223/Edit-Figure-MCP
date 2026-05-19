"""Export draw.io files to PNG via a remote renderer."""

from __future__ import annotations

from pathlib import Path

import requests


BASE_URL = "https://huanghe1223-terminal.ms.fun"
DRAWIO_FILE = Path("test_drawio_export/template.drawio")
OUTPUT_FILE = Path("test_drawio_export/template.png")


def export_drawio_to_png(
    drawio_file: str | Path,
    output_file: str | Path,
    *,
    base_url: str = BASE_URL,
    timeout: int = 120,
    verbose: bool = True,
) -> Path:
    drawio_path = Path(drawio_file)
    output_path = Path(output_file)

    if not drawio_path.is_file():
        raise FileNotFoundError(f"Drawio file not found: {drawio_path}")

    xml = drawio_path.read_text(encoding="utf-8")
    url = f"{base_url.rstrip('/')}/export"

    response = requests.post(
        url,
        data={
            "format": "png",
            "xml": xml,
        },
        timeout=timeout,
    )

    if verbose:
        print(f"Status code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")

    if not response.ok:
        if verbose:
            print("Response text:")
            print(response.text[:2000])
        raise RuntimeError(f"Export failed with status {response.status_code}")

    if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
        if verbose:
            print("Warning: response is not a PNG")
            print(response.content[:500])
        raise RuntimeError("Export failed: response is not a PNG")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    if verbose:
        size_kb = output_path.stat().st_size / 1024
        print(f"Exported: {output_path}")
        print(f"File size: {size_kb:.2f} KB")

    return output_path


def run() -> Path:
    return export_drawio_to_png(DRAWIO_FILE, OUTPUT_FILE)


def main() -> None:
    export_drawio_to_png(DRAWIO_FILE, OUTPUT_FILE)


if __name__ == "__main__":
    main()
