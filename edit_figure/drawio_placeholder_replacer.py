"""Replace draw.io placeholders with RMBG outputs.

Outputs:
- final.drawio
"""

from __future__ import annotations

import base64
import json
import xml.etree.ElementTree as ET
from pathlib import Path


# ---- Hardcoded configuration ----
ICON_INFOS_JSON = (
    "outputs/example/icon_infos.json"
)
TEMPLATE_DRAWIO = "outputs/example/template.drawio"
OUTPUT_DRAWIO = "outputs/example/final.drawio"


def _load_icon_infos(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    raise ValueError("icon_infos.json must be a list")


def _image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _find_cell_by_id(root: ET.Element, cell_id: str) -> ET.Element | None:
    return root.find(f".//mxCell[@id='{cell_id}']")


def replace_drawio_placeholders(
    icon_infos_json: str | Path,
    template_drawio: str | Path,
    output_drawio: str | Path,
) -> dict:
    """Replace draw.io placeholder cells with transparent PNG icons."""
    icon_infos_path = Path(icon_infos_json)
    template_drawio_path = Path(template_drawio)
    output_drawio_path = Path(output_drawio)
    output_drawio_path.parent.mkdir(parents=True, exist_ok=True)

    if not icon_infos_path.is_file():
        raise FileNotFoundError(f"icon_infos.json not found: {icon_infos_path}")
    if not template_drawio_path.is_file():
        raise FileNotFoundError(f"template.drawio not found: {template_drawio_path}")

    icon_infos = _load_icon_infos(icon_infos_path)

    tree = ET.parse(str(template_drawio_path))
    root = tree.getroot()

    replaced_count = 0
    missing_placeholders = []
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

        cell = _find_cell_by_id(root, label_clean)
        if cell is None:
            print(f"Placeholder not found in drawio: {label_clean}")
            missing_placeholders.append(label_clean)
            continue

        x1 = str(info.get("x1", 0))
        y1 = str(info.get("y1", 0))
        width = str(info.get("width", 0))
        height = str(info.get("height", 0))

        image_b64 = _image_to_base64(nobg_path)
        style = (
            "shape=image;"
            "html=1;"
            "imageAspect=0;"
            "aspect=fixed;"
            f"image=data:image/png%3Bbase64,{image_b64};"
        )

        cell.set("style", style)
        cell.set("value", "")
        cell.set("vertex", "1")

        geometry = cell.find("mxGeometry")
        if geometry is None:
            geometry = ET.SubElement(cell, "mxGeometry")
            geometry.set("as", "geometry")

        geometry.set("x", x1)
        geometry.set("y", y1)
        geometry.set("width", width)
        geometry.set("height", height)

        print(f"Replaced: {label_clean}")
        replaced_count += 1

    tree.write(str(output_drawio_path), encoding="utf-8", xml_declaration=True)
    print(f"Saved: {output_drawio_path}")

    return {
        "output_path": str(output_drawio_path),
        "replaced_count": replaced_count,
        "missing_placeholders": missing_placeholders,
        "missing_icons": missing_icons,
    }


def run() -> dict:
    return replace_drawio_placeholders(
        icon_infos_json=ICON_INFOS_JSON,
        template_drawio=TEMPLATE_DRAWIO,
        output_drawio=OUTPUT_DRAWIO,
    )


def main() -> None:
    replace_drawio_placeholders(
        icon_infos_json=ICON_INFOS_JSON,
        template_drawio=TEMPLATE_DRAWIO,
        output_drawio=OUTPUT_DRAWIO,
    )


if __name__ == "__main__":
    main()
