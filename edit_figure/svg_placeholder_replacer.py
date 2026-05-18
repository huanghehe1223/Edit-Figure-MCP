"""Replace SVG icon placeholders with RMBG outputs.

Outputs:
- final.svg
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path


# ---- Hardcoded configuration ----
ICON_INFOS_JSON = (
    "outputs/example/icon_infos.json"
)
TEMPLATE_SVG = "outputs/example/template.svg"
OUTPUT_SVG = "outputs/example/final.svg"


def _load_icon_infos(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    raise ValueError("icon_infos.json must be a list")


def _image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _replace_group(svg_text: str, label_clean: str, image_tag: str) -> tuple[str, bool]:
    group_pattern = rf'<g[^>]*\bid=["\']{re.escape(label_clean)}["\'][^>]*>[\s\S]*?</g>'
    if re.search(group_pattern, svg_text, flags=re.IGNORECASE):
        svg_text = re.sub(group_pattern, image_tag, svg_text, count=1, flags=re.IGNORECASE)
        return svg_text, True

    rect_pattern = rf'<rect[^>]*\bid=["\']{re.escape(label_clean)}["\'][^>]*/?>'
    if re.search(rect_pattern, svg_text, flags=re.IGNORECASE):
        svg_text = re.sub(rect_pattern, image_tag, svg_text, count=1, flags=re.IGNORECASE)
        return svg_text, True

    return svg_text, False


def replace_svg_placeholders(
    icon_infos_json: str | Path,
    template_svg: str | Path,
    output_svg: str | Path,
) -> dict:
    """Replace SVG placeholder groups/rects with transparent PNG icons."""
    icon_infos_path = Path(icon_infos_json)
    template_svg_path = Path(template_svg)
    output_svg_path = Path(output_svg)
    output_svg_path.parent.mkdir(parents=True, exist_ok=True)

    if not icon_infos_path.is_file():
        raise FileNotFoundError(f"icon_infos.json not found: {icon_infos_path}")
    if not template_svg_path.is_file():
        raise FileNotFoundError(f"template.svg not found: {template_svg_path}")

    icon_infos = _load_icon_infos(icon_infos_path)
    svg_text = template_svg_path.read_text(encoding="utf-8")

    replaced_count = 0
    appended_count = 0
    missing_icons = []

    for info in icon_infos:
        label_clean = str(info.get("label_clean", "")).strip()
        if not label_clean:
            print("Skip icon with empty label_clean")
            continue

        nobg_path = Path(str(info.get("nobg_path", "")))
        if not nobg_path.is_file():
            print(f"Missing nobg icon: {nobg_path}")
            missing_icons.append(str(nobg_path))
            continue

        x1 = float(info.get("x1", 0))
        y1 = float(info.get("y1", 0))
        width = float(info.get("width", 0))
        height = float(info.get("height", 0))
        if width <= 0 or height <= 0:
            x2 = float(info.get("x2", x1))
            y2 = float(info.get("y2", y1))
            width = max(0.0, x2 - x1)
            height = max(0.0, y2 - y1)

        image_b64 = _image_to_base64(nobg_path)
        image_tag = (
            f'<image id="icon_{label_clean}" x="{x1}" y="{y1}" '
            f'width="{width}" height="{height}" '
            f'href="data:image/png;base64,{image_b64}" '
            f'preserveAspectRatio="xMidYMid meet"/>'
        )

        svg_text, replaced = _replace_group(svg_text, label_clean, image_tag)
        if replaced:
            replaced_count += 1
        else:
            svg_text = svg_text.replace("</svg>", f"  {image_tag}\n</svg>")
            print(f"Placeholder not found; appended icon {label_clean}")
            appended_count += 1

    output_svg_path.write_text(svg_text, encoding="utf-8")
    print(f"Saved: {output_svg_path}")

    return {
        "output_path": str(output_svg_path),
        "replaced_count": replaced_count,
        "appended_count": appended_count,
        "missing_icons": missing_icons,
    }


def run() -> dict:
    return replace_svg_placeholders(
        icon_infos_json=ICON_INFOS_JSON,
        template_svg=TEMPLATE_SVG,
        output_svg=OUTPUT_SVG,
    )


def main() -> None:
    replace_svg_placeholders(
        icon_infos_json=ICON_INFOS_JSON,
        template_svg=TEMPLATE_SVG,
        output_svg=OUTPUT_SVG,
    )


if __name__ == "__main__":
    main()
