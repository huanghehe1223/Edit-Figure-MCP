"""Crop icon regions from a figure using ``boxlib.json``.

Outputs:
- icons/icon_AF01.png, icon_AF02.png, ...
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


# ---- Hardcoded configuration ----
IMAGE_PATH = "sample_images/example.png"
BOXLIB_PATH = f"outputs/{Path(IMAGE_PATH).stem}/boxlib.json"
OUTPUT_DIR = f"outputs/{Path(IMAGE_PATH).stem}/icons"


def _label_to_filename(label: str, fallback_id: int) -> str:
    if label:
        clean = label.replace("<", "").replace(">", "")
        return f"icon_{clean}.png"
    return f"icon_AF{fallback_id + 1:02d}.png"


def crop_icons(
    image_path: str | Path,
    boxlib_path: str | Path,
    output_dir: str | Path,
) -> dict:
    """Crop detected icon boxes from an image.

    Args:
        image_path: Source image path.
        boxlib_path: JSON file produced by SAM3 segmentation.
        output_dir: Directory for cropped icon PNGs.

    Returns:
        Metadata for the generated crops.
    """
    image_path = Path(image_path)
    boxlib_path = Path(boxlib_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not boxlib_path.is_file():
        raise FileNotFoundError(f"Boxlib not found: {boxlib_path}")

    with Image.open(str(image_path)) as image:
        with boxlib_path.open("r", encoding="utf-8") as f:
            boxlib = json.load(f)

        boxes = boxlib.get("boxes", [])
        if not boxes:
            print("No boxes found; nothing to crop.")
            return {"output_dir": str(output_dir), "icons": [], "count": 0}

        icons = []
        for idx, box in enumerate(boxes):
            x1 = int(box.get("x1", 0))
            y1 = int(box.get("y1", 0))
            x2 = int(box.get("x2", 0))
            y2 = int(box.get("y2", 0))

            if x2 <= x1 or y2 <= y1:
                print(f"Skip invalid box #{idx}: ({x1}, {y1}, {x2}, {y2})")
                continue

            label = str(box.get("label", ""))
            filename = _label_to_filename(label, idx)
            output_path = output_dir / filename

            cropped = image.crop((x1, y1, x2, y2))
            cropped.save(str(output_path))
            icons.append(
                {
                    "id": box.get("id", idx),
                    "label": label,
                    "path": str(output_path),
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )
            print(f"Saved: {output_path}")

    return {"output_dir": str(output_dir), "icons": icons, "count": len(icons)}


def run() -> dict:
    return crop_icons(
        image_path=IMAGE_PATH,
        boxlib_path=BOXLIB_PATH,
        output_dir=OUTPUT_DIR,
    )


def main() -> None:
    crop_icons(
        image_path=IMAGE_PATH,
        boxlib_path=BOXLIB_PATH,
        output_dir=OUTPUT_DIR,
    )


if __name__ == "__main__":
    main()
