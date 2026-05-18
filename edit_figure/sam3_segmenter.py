"""SAM3 icon detection via Roboflow.

Hardcoded inputs produce:
- samed.png (gray placeholders with labels)
- boxlib.json (detected boxes + metadata)
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import time
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont


# ---- Hardcoded configuration ----
IMAGE_PATH = "sample_images/original_3.jpg"
OUTPUT_DIR = f"outputs/{Path(IMAGE_PATH).stem}"
TEXT_PROMPTS = "robot,person,cat,dog,clock,calendar,headset,computer,brain"
MIN_SCORE = 0.5
MERGE_THRESHOLD = 0.01
# Size filter: drop boxes too small relative to the image size.
MIN_WIDTH_RATIO = 0.02
MIN_HEIGHT_RATIO = 0.02

SAM3_ROBOFLOW_API_URL = os.environ.get(
    "ROBOFLOW_API_URL",
    "https://serverless.roboflow.com/sam3/concept_segment",
)
SAM3_API_TIMEOUT = 300
BOXLIB_NO_ICON_MODE_KEY = "no_icon_mode"


def get_label_font(box_width: int, box_height: int) -> Optional[ImageFont.FreeTypeFont]:
    min_dim = min(box_width, box_height)
    font_size = max(12, min(48, min_dim // 4))

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, font_size)
        except (IOError, OSError):
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return None


def calculate_overlap_ratio(box1: dict, box2: dict) -> float:
    x1 = max(box1["x1"], box2["x1"])
    y1 = max(box1["y1"], box2["y1"])
    x2 = min(box1["x2"], box2["x2"])
    y2 = min(box1["y2"], box2["y2"])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1["x2"] - box1["x1"]) * (box1["y2"] - box1["y1"])
    area2 = (box2["x2"] - box2["x1"]) * (box2["y2"] - box2["y1"])

    if area1 == 0 or area2 == 0:
        return 0.0

    return intersection / min(area1, area2)


def merge_two_boxes(box1: dict, box2: dict) -> dict:
    merged = {
        "x1": min(box1["x1"], box2["x1"]),
        "y1": min(box1["y1"], box2["y1"]),
        "x2": max(box1["x2"], box2["x2"]),
        "y2": max(box1["y2"], box2["y2"]),
        "score": max(box1.get("score", 0), box2.get("score", 0)),
    }

    prompt1 = box1.get("prompt", "")
    prompt2 = box2.get("prompt", "")
    if prompt1 and prompt2:
        if prompt1 == prompt2:
            merged["prompt"] = prompt1
        else:
            merged["prompt"] = prompt1 if box1.get("score", 0) >= box2.get("score", 0) else prompt2
    elif prompt1:
        merged["prompt"] = prompt1
    elif prompt2:
        merged["prompt"] = prompt2

    return merged


def merge_overlapping_boxes(boxes: list[dict], overlap_threshold: float = 0.9) -> list[dict]:
    if overlap_threshold <= 0 or len(boxes) <= 1:
        return boxes

    working_boxes = [box.copy() for box in boxes]
    merged = True

    while merged:
        merged = False
        n = len(working_boxes)

        for i in range(n):
            if merged:
                break
            for j in range(i + 1, n):
                ratio = calculate_overlap_ratio(working_boxes[i], working_boxes[j])
                if ratio >= overlap_threshold:
                    new_box = merge_two_boxes(working_boxes[i], working_boxes[j])
                    working_boxes = [working_boxes[k] for k in range(n) if k not in (i, j)]
                    working_boxes.append(new_box)
                    merged = True
                    break

    result = []
    for idx, box in enumerate(working_boxes):
        result_box = {
            "id": idx,
            "label": f"<AF>{idx + 1:02d}",
            "x1": box["x1"],
            "y1": box["y1"],
            "x2": box["x2"],
            "y2": box["y2"],
            "score": box.get("score", 0),
        }
        if "prompt" in box:
            result_box["prompt"] = box["prompt"]
        result.append(result_box)

    return result


def expand_box_bounds(
    box: dict,
    image_width: int,
    image_height: int,
    margin: int = 2,
) -> dict:
    x1 = max(0, box["x1"] - margin)
    y1 = max(0, box["y1"] - margin)
    x2 = min(image_width, box["x2"] + margin)
    y2 = min(image_height, box["y2"] + margin)

    if x2 <= x1:
        x2 = min(image_width, x1 + 1)
    if y2 <= y1:
        y2 = min(image_height, y1 + 1)

    expanded = box.copy()
    expanded.update({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return expanded


def _get_roboflow_api_key(api_key: Optional[str] = None) -> str:
    if api_key:
        return api_key
    key = os.environ.get("ROBOFLOW_API_KEY") or os.environ.get("API_KEY")
    if not key:
        raise ValueError("Missing ROBOFLOW_API_KEY (or API_KEY) in environment.")
    return key


def _image_to_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _polygon_to_bbox(points: list, width: int, height: int) -> Optional[tuple[int, int, int, int]]:
    xs: list[float] = []
    ys: list[float] = []

    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            x = float(pt[0])
            y = float(pt[1])
        except (TypeError, ValueError):
            continue
        xs.append(x)
        ys.append(y)

    if not xs or not ys:
        return None

    x1 = int(round(min(xs)))
    y1 = int(round(min(ys)))
    x2 = int(round(max(xs)))
    y2 = int(round(max(ys)))

    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    x2 = max(0, min(width, x2))
    y2 = max(0, min(height, y2))

    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _extract_roboflow_detections(response_json: dict, image_size: tuple[int, int]) -> list[dict]:
    width, height = image_size
    detections: list[dict] = []

    prompt_results = response_json.get("prompt_results") if isinstance(response_json, dict) else None
    if not isinstance(prompt_results, list):
        return detections

    for prompt_result in prompt_results:
        if not isinstance(prompt_result, dict):
            continue
        predictions = prompt_result.get("predictions", [])
        if not isinstance(predictions, list):
            continue
        for prediction in predictions:
            if not isinstance(prediction, dict):
                continue
            confidence = prediction.get("confidence")
            masks = prediction.get("masks", [])
            if not isinstance(masks, list):
                continue
            for mask in masks:
                points = []
                if isinstance(mask, list) and mask:
                    if isinstance(mask[0], (list, tuple)) and len(mask[0]) >= 2 and isinstance(
                        mask[0][0], (int, float)
                    ):
                        points = mask
                    elif isinstance(mask[0], (list, tuple)):
                        for sub in mask:
                            if isinstance(sub, (list, tuple)) and len(sub) >= 2 and isinstance(
                                sub[0], (int, float)
                            ):
                                points.append(sub)
                            elif isinstance(sub, (list, tuple)) and sub and isinstance(
                                sub[0], (list, tuple)
                            ):
                                for pt in sub:
                                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                        points.append(pt)
                if not points:
                    continue
                xyxy = _polygon_to_bbox(points, width, height)
                if not xyxy:
                    continue
                detections.append(
                    {
                        "x1": xyxy[0],
                        "y1": xyxy[1],
                        "x2": xyxy[2],
                        "y2": xyxy[3],
                        "score": confidence,
                    }
                )

    return detections


def _call_sam3_roboflow_api(
    image_base64: str,
    prompt: str,
    api_key: str,
    min_score: float,
) -> dict:
    payload = {
        "image": {"type": "base64", "value": image_base64},
        "prompts": [{"type": "text", "text": prompt}],
        "format": "polygon",
        "output_prob_thresh": min_score,
    }

    retry_count = max(1, int(os.environ.get("SAM3_API_RETRIES", "3")))
    retry_delay = max(0.0, float(os.environ.get("SAM3_API_RETRY_DELAY", "1.5")))

    last_error: Optional[Exception] = None
    url = f"{SAM3_ROBOFLOW_API_URL}?api_key={api_key}"

    for attempt in range(1, retry_count + 1):
        try:
            response = requests.post(url, json=payload, timeout=SAM3_API_TIMEOUT)
            if response.status_code != 200:
                raise RuntimeError(f"Roboflow API error: {response.status_code} - {response.text[:500]}")
            result = response.json()
            if isinstance(result, dict) and "error" in result:
                raise RuntimeError(f"Roboflow API error: {result.get('error')}")
            return result
        except Exception as exc:
            last_error = exc
            if attempt < retry_count:
                sleep_s = retry_delay * (2 ** (attempt - 1))
                print(f"Roboflow request failed ({attempt}/{retry_count}): {exc}. Retry in {sleep_s:.1f}s")
                time.sleep(sleep_s)
                continue
            break

    if last_error is not None:
        raise last_error
    raise RuntimeError("Roboflow request failed: unknown error")


def segment_with_sam3(
    image_path: str | Path,
    output_dir: str | Path,
    text_prompts: str,
    min_score: float = MIN_SCORE,
    merge_threshold: float = MERGE_THRESHOLD,
    min_width_ratio: float = MIN_WIDTH_RATIO,
    min_height_ratio: float = MIN_HEIGHT_RATIO,
    api_key: Optional[str] = None,
) -> dict:
    """Detect icon-like objects and write ``samed.png`` plus ``boxlib.json``.

    Args:
        image_path: Source image path.
        output_dir: Directory for segmentation outputs.
        text_prompts: Comma-separated concepts for SAM3/Roboflow.
        min_score: Detection confidence threshold.
        merge_threshold: Overlap threshold used to merge near-duplicate boxes.
        min_width_ratio: Minimum box width relative to image width.
        min_height_ratio: Minimum box height relative to image height.
        api_key: Optional Roboflow API key. Falls back to environment variables.

    Returns:
        Paths and detected boxes metadata.
    """
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(str(image_path))
    original_size = image.size
    image_width, image_height = original_size

    prompt_list = [p.strip() for p in text_prompts.split(",") if p.strip()]
    print(f"Image: {image_path}")
    print(f"Image size: {original_size[0]} x {original_size[1]}")
    print(f"Prompts: {prompt_list}")
    print(
        "Min size ratio filter: "
        f"width<{min_width_ratio:.3f} or height<{min_height_ratio:.3f} (relative to image size)"
    )

    api_key = _get_roboflow_api_key(api_key)
    image_base64 = _image_to_base64(image)

    all_detected_boxes: list[dict] = []
    total_detected = 0

    for prompt in prompt_list:
        print(f"\nDetecting: '{prompt}'")
        response_json = _call_sam3_roboflow_api(
            image_base64=image_base64,
            prompt=prompt,
            api_key=api_key,
            min_score=min_score,
        )
        detections = _extract_roboflow_detections(response_json, original_size)
        prompt_count = 0
        for det in detections:
            score = det.get("score")
            score_val = float(score) if score is not None else 0.0
            if score_val >= min_score:
                all_detected_boxes.append(
                    {
                        "x1": det["x1"],
                        "y1": det["y1"],
                        "x2": det["x2"],
                        "y2": det["y2"],
                        "score": score_val,
                        "prompt": prompt,
                    }
                )
                prompt_count += 1
            else:
                print(f"  skip: score={score_val:.3f} < {min_score}")
        print(f"  {prompt_count} detections")
        total_detected += prompt_count

    print(f"\nTotal detections: {total_detected} (from {len(prompt_list)} prompts)")

    valid_boxes = []
    for i, box_data in enumerate(all_detected_boxes):
        valid_boxes.append(
            {
                "id": i,
                "label": f"<AF>{i + 1:02d}",
                "x1": box_data["x1"],
                "y1": box_data["y1"],
                "x2": box_data["x2"],
                "y2": box_data["y2"],
                "score": box_data["score"],
                "prompt": box_data["prompt"],
            }
        )

    if merge_threshold > 0 and len(valid_boxes) > 1:
        print(f"\nMerging overlapping boxes (threshold={merge_threshold})...")
        original_count = len(valid_boxes)
        valid_boxes = merge_overlapping_boxes(valid_boxes, merge_threshold)
        merged_count = original_count - len(valid_boxes)
        if merged_count > 0:
            print(f"Merged: {original_count} -> {len(valid_boxes)} (merged {merged_count})")
        else:
            print("No merges applied")

    expanded_boxes = [
        expand_box_bounds(box, original_size[0], original_size[1], margin=2)
        for box in valid_boxes
    ]

    filtered_boxes = []
    dropped_small = 0
    for box in expanded_boxes:
        width = box["x2"] - box["x1"]
        height = box["y2"] - box["y1"]
        width_ratio = width / float(image_width) if image_width else 0.0
        height_ratio = height / float(image_height) if image_height else 0.0
        if width_ratio < min_width_ratio or height_ratio < min_height_ratio:
            dropped_small += 1
            print(
                "Drop small box: "
                f"w={width}px ({width_ratio:.4f}), h={height}px ({height_ratio:.4f}), "
                f"min_w={min_width_ratio:.4f}, min_h={min_height_ratio:.4f}"
            )
            continue
        filtered_boxes.append(box)

    if dropped_small:
        print(f"Dropped small boxes: {dropped_small}")
    valid_boxes = filtered_boxes

    renumbered_boxes = []
    for idx, box in enumerate(valid_boxes):
        updated = box.copy()
        updated["id"] = idx
        updated["label"] = f"<AF>{idx + 1:02d}"
        updated["width"] = updated["x2"] - updated["x1"]
        updated["height"] = updated["y2"] - updated["y1"]
        renumbered_boxes.append(updated)
    valid_boxes = renumbered_boxes

    samed_image = image.copy()
    draw = ImageDraw.Draw(samed_image)

    for box_info in valid_boxes:
        x1, y1, x2, y2 = box_info["x1"], box_info["y1"], box_info["x2"], box_info["y2"]
        label = box_info["label"]
        draw.rectangle([x1, y1, x2, y2], fill="#808080", outline="black", width=3)

        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        font = get_label_font(x2 - x1, y2 - y1)
        if font:
            try:
                draw.text((cx, cy), label, fill="white", anchor="mm", font=font)
            except TypeError:
                bbox = draw.textbbox((0, 0), label, font=font)
                text_x = cx - (bbox[2] - bbox[0]) // 2
                text_y = cy - (bbox[3] - bbox[1]) // 2
                draw.text((text_x, text_y), label, fill="white", font=font)
        else:
            draw.text((cx, cy), label, fill="white")

    samed_path = output_dir / "samed.png"
    samed_image.save(str(samed_path))

    boxlib_data = {
        "image_size": {"width": original_size[0], "height": original_size[1]},
        "prompts_used": prompt_list,
        "boxes": valid_boxes,
        BOXLIB_NO_ICON_MODE_KEY: len(valid_boxes) == 0,
    }

    boxlib_path = output_dir / "boxlib.json"
    with open(boxlib_path, "w", encoding="utf-8") as f:
        json.dump(boxlib_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {samed_path}")
    print(f"Saved: {boxlib_path}")

    return {
        "output_dir": str(output_dir),
        "samed_path": str(samed_path),
        "boxlib_path": str(boxlib_path),
        "boxes": valid_boxes,
        "box_count": len(valid_boxes),
        "prompts_used": prompt_list,
    }


def run() -> dict:
    return segment_with_sam3(
        image_path=IMAGE_PATH,
        output_dir=OUTPUT_DIR,
        text_prompts=TEXT_PROMPTS,
        min_score=MIN_SCORE,
        merge_threshold=MERGE_THRESHOLD,
        min_width_ratio=MIN_WIDTH_RATIO,
        min_height_ratio=MIN_HEIGHT_RATIO,
    )


def main() -> None:
    segment_with_sam3(
        image_path=IMAGE_PATH,
        output_dir=OUTPUT_DIR,
        text_prompts=TEXT_PROMPTS,
        min_score=MIN_SCORE,
        merge_threshold=MERGE_THRESHOLD,
        min_width_ratio=MIN_WIDTH_RATIO,
        min_height_ratio=MIN_HEIGHT_RATIO,
    )


if __name__ == "__main__":
    main()
