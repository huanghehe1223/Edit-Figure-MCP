"""Export SVG files to PNG using CairoSVG."""

from __future__ import annotations

from pathlib import Path

import cairosvg


DEFAULT_SVG = Path("final.svg")
DEFAULT_PNG = Path("final.png")


def export_svg_to_png(
    svg_file: str | Path,
    output_file: str | Path,
    *,
    verbose: bool = True,
) -> Path:
    svg_path = Path(svg_file)
    output_path = Path(output_file)

    if not svg_path.is_file():
        raise FileNotFoundError(f"SVG file not found: {svg_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(svg_path), write_to=str(output_path))

    if verbose:
        print(f"Converted: {svg_path} -> {output_path}")

    return output_path


def run() -> Path:
    return export_svg_to_png(DEFAULT_SVG, DEFAULT_PNG)


def main() -> None:
    export_svg_to_png(DEFAULT_SVG, DEFAULT_PNG)


if __name__ == "__main__":
    main()
