"""RMBG-2.0 batch background removal for cropped icons.

Outputs:
- icon_AF01_nobg.png, icon_AF02_nobg.png, ...
- icon_infos.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image


# ---- Hardcoded configuration ----
MODEL_DIR = "models/RMBG-2.0"
ICONS_DIR = "outputs/example/icons"
BOXLIB_PATH = "outputs/example/boxlib.json"
OUTPUT_DIR = "outputs/example/icons_nobg"
ICON_INFOS_JSON = f"{OUTPUT_DIR}/icon_infos.json"
TARGET_SIZE = (512, 512)
BATCH_SIZE = 8
#是否强制gpu
FORCE_GPU = True


def letterbox_image(
    image: Image.Image,
    target_size: Tuple[int, int],
) -> Tuple[Image.Image, Dict[str, object]]:
    target_w, target_h = target_size
    orig_w, orig_h = image.size

    scale = min(target_w / orig_w, target_h / orig_h)
    resized_w = max(1, int(round(orig_w * scale)))
    resized_h = max(1, int(round(orig_h * scale)))

    resized = image.resize((resized_w, resized_h), resample=Image.LANCZOS)
    padded = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    pad_left = (target_w - resized_w) // 2
    pad_top = (target_h - resized_h) // 2
    padded.paste(resized, (pad_left, pad_top))

    meta = {
        "pad_left": pad_left,
        "pad_top": pad_top,
        "resized_size": (resized_w, resized_h),
        "original_size": (orig_w, orig_h),
    }
    return padded, meta


def iter_batches(items: List[Path], batch_size: int) -> List[List[Path]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _label_clean(label: str, fallback_id: int) -> str:
    if label:
        return label.replace("<", "").replace(">", "")
    return f"AF{fallback_id + 1:02d}"


def get_rmbg_device() -> str:
    import torch

    requested_device = os.environ.get("RMBG_DEVICE", "").strip().lower()
    if requested_device in {"cpu", "cuda"}:
        if requested_device == "cuda" and not torch.cuda.is_available():
            print("RMBG_DEVICE=cuda requested, but CUDA is unavailable; falling back to CPU.")
            return "cpu"
        return requested_device

    if FORCE_GPU:
        if torch.cuda.is_available():
            return "cuda"
        print("FORCE_GPU is enabled, but CUDA is unavailable; falling back to CPU.")
        return "cpu"

    return "cuda" if torch.cuda.is_available() else "cpu"


def remove_icon_backgrounds(
    model_dir: str | Path,
    icons_dir: str | Path,
    boxlib_path: str | Path,
    output_dir: str | Path,
    icon_infos_json: str | Path | None = None,
    target_size: Tuple[int, int] = TARGET_SIZE,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Remove backgrounds from cropped icons and write ``icon_infos.json``.

    Args:
        model_dir: Local RMBG-2.0 model directory.
        icons_dir: Directory containing cropped ``icon_AFxx.png`` files.
        boxlib_path: JSON file containing source box coordinates.
        output_dir: Directory for transparent-background icon PNGs.
        icon_infos_json: Output metadata path. Defaults to output_dir/icon_infos.json.
        target_size: Letterbox size used by RMBG.
        batch_size: Inference batch size.

    Returns:
        Metadata for generated transparent icons.
    """
    model_dir = Path(model_dir)
    icons_dir = Path(icons_dir)
    boxlib_path = Path(boxlib_path)
    output_dir = Path(output_dir)
    icon_infos_json = Path(icon_infos_json) if icon_infos_json else output_dir / "icon_infos.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not model_dir.exists():
        raise FileNotFoundError(f"Model dir not found: {model_dir}")
    if not icons_dir.exists():
        raise FileNotFoundError(f"Icons dir not found: {icons_dir}")
    if not boxlib_path.exists():
        raise FileNotFoundError(f"Boxlib not found: {boxlib_path}")

    with boxlib_path.open("r", encoding="utf-8") as f:
        boxlib = json.load(f)

    device = get_rmbg_device()

    boxes = boxlib.get("boxes", [])
    if not boxes:
        print("No boxes found in boxlib.json; nothing to process.")
        icon_infos_json.write_text("[]\n", encoding="utf-8")
        return {
            "output_dir": str(output_dir),
            "icon_infos_json": str(icon_infos_json),
            "icons": [],
            "count": 0,
            "device": device,
        }

    icon_entries: List[dict] = []
    for idx, box in enumerate(boxes):
        label = str(box.get("label", ""))
        label_clean = _label_clean(label, idx)
        crop_path = icons_dir / f"icon_{label_clean}.png"
        if not crop_path.exists():
            print(f"Missing crop for box #{idx}: {crop_path}")
            continue
        icon_entries.append(
            {
                "box": box,
                "label": label,
                "label_clean": label_clean,
                "crop_path": crop_path,
            }
        )

    if not icon_entries:
        print("No cropped icons found to process.")
        icon_infos_json.write_text("[]\n", encoding="utf-8")
        return {
            "output_dir": str(output_dir),
            "icon_infos_json": str(icon_infos_json),
            "icons": [],
            "count": 0,
            "device": device,
        }

    from torchvision import transforms
    from transformers import AutoModelForImageSegmentation

    import torch

    print(f"Device: {device}")
    print(f"Model: {model_dir}")
    print(f"Icons: {len(icon_entries)}")

    model = AutoModelForImageSegmentation.from_pretrained(
        str(model_dir),
        trust_remote_code=True,
    ).eval()
    try:
        model = model.to(device)
    except RuntimeError as exc:
        if device != "cuda":
            raise
        print(f"CUDA initialization failed ({exc}); falling back to CPU.")
        device = "cpu"
        model = model.to(device)

    transform_image = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    icon_infos = []

    for batch in iter_batches(icon_entries, batch_size):
        originals: List[Image.Image] = []
        metas: List[Dict[str, object]] = []
        tensors: List[torch.Tensor] = []

        for entry in batch:
            image = Image.open(entry["crop_path"]).convert("RGB")
            padded, meta = letterbox_image(image, target_size)
            tensor = transform_image(padded)

            originals.append(image)
            metas.append(meta)
            tensors.append(tensor)

        batch_tensor = torch.stack(tensors).to(device)
        with torch.no_grad():
            pred = model(batch_tensor)[-1].sigmoid().cpu()

        for idx, entry in enumerate(batch):
            mask = pred[idx].squeeze(0)
            mask_pil = transforms.ToPILImage()(mask)

            pad_left = int(metas[idx]["pad_left"])
            pad_top = int(metas[idx]["pad_top"])
            resized_w, resized_h = metas[idx]["resized_size"]
            orig_w, orig_h = metas[idx]["original_size"]

            mask_pil = mask_pil.crop((pad_left, pad_top, pad_left + resized_w, pad_top + resized_h))
            mask_pil = mask_pil.resize((orig_w, orig_h), resample=Image.BILINEAR)

            output = originals[idx].copy()
            output.putalpha(mask_pil)

            label_clean = entry["label_clean"]
            output_path = output_dir / f"icon_{label_clean}_nobg.png"
            output.save(output_path)

            box = entry["box"]
            box_id = int(box.get("id", idx))
            x1 = int(box.get("x1", 0))
            y1 = int(box.get("y1", 0))
            x2 = int(box.get("x2", 0))
            y2 = int(box.get("y2", 0))

            icon_infos.append(
                {
                    "id": box_id,
                    "label": entry["label"],
                    "label_clean": label_clean,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "crop_path": str(entry["crop_path"]),
                    "nobg_path": str(output_path),
                    "original_size": [orig_w, orig_h],
                    "resized_size": [int(resized_w), int(resized_h)],
                    "pad_left": pad_left,
                    "pad_top": pad_top,
                }
            )

            print(f"Saved: {output_path}")

    with icon_infos_json.open("w", encoding="utf-8") as f:
        json.dump(icon_infos, f, indent=2, ensure_ascii=False)
    print(f"Saved: {icon_infos_json}")

    return {
        "output_dir": str(output_dir),
        "icon_infos_json": str(icon_infos_json),
        "icons": icon_infos,
        "count": len(icon_infos),
        "device": device,
    }


def run() -> dict:
    return remove_icon_backgrounds(
        model_dir=MODEL_DIR,
        icons_dir=ICONS_DIR,
        boxlib_path=BOXLIB_PATH,
        output_dir=OUTPUT_DIR,
        icon_infos_json=ICON_INFOS_JSON,
        target_size=TARGET_SIZE,
        batch_size=BATCH_SIZE,
    )


def main() -> None:
    remove_icon_backgrounds(
        model_dir=MODEL_DIR,
        icons_dir=ICONS_DIR,
        boxlib_path=BOXLIB_PATH,
        output_dir=OUTPUT_DIR,
        icon_infos_json=ICON_INFOS_JSON,
        target_size=TARGET_SIZE,
        batch_size=BATCH_SIZE,
    )


if __name__ == "__main__":
    main()
