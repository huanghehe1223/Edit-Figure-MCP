"""MCP server for converting figures into editable draw.io/SVG files."""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import threading
import traceback
from pathlib import Path
from typing import Annotated, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from edit_figure.background_remover import remove_icon_backgrounds
from edit_figure.drawio_placeholder_replacer import replace_drawio_placeholders
from edit_figure.icon_cropper import crop_icons
from edit_figure.sam3_segmenter import segment_with_sam3
from edit_figure.svg_placeholder_replacer import replace_svg_placeholders


mcp = FastMCP("edit-figure")

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_RMBG_MODEL_DIR = Path(
    os.environ.get("RMBG_MODEL_DIR", PROJECT_DIR / "models" / "RMBG-2.0")
)
DEV_RMBG_MODEL_DIR = PROJECT_DIR.parent / "rmbg" / "models" / "RMBG-2.0"

CALL_LOCK = threading.RLock()
SUPPORTED_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


@contextlib.contextmanager
def _capture_output():
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        yield stdout, stderr


def _call_with_logs(func, *args, **kwargs) -> tuple[dict, str]:
    with CALL_LOCK:
        with _capture_output() as (stdout, stderr):
            result = func(*args, **kwargs)
    return result, _truncate_log(stdout.getvalue() + stderr.getvalue())


def _truncate_log(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _resolve_workspace(workspace_dir: str) -> Path:
    raw_workspace_path = Path(workspace_dir).expanduser()
    if not raw_workspace_path.is_absolute():
        raise ValueError("workspace_dir must be an absolute path")

    workspace_path = raw_workspace_path.resolve()
    if not workspace_path.exists():
        raise FileNotFoundError(f"Workspace directory does not exist: {workspace_path}")
    if not workspace_path.is_dir():
        raise ValueError(f"workspace_dir is not a directory: {workspace_path}")
    return workspace_path


def _resolve_relative_path(
    workspace_path: Path,
    relative_path: str,
    *,
    param_name: str,
    must_exist: bool = True,
    must_be_file: bool = True,
) -> Path:
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise ValueError(f"{param_name} must be relative to workspace_dir")

    resolved_path = (workspace_path / raw_path).resolve()
    try:
        resolved_path.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError(f"{param_name} escapes workspace_dir") from exc

    if must_exist and not resolved_path.exists():
        raise FileNotFoundError(f"{param_name} does not exist: {relative_path}")
    if must_exist and must_be_file and not resolved_path.is_file():
        raise ValueError(f"{param_name} is not a file: {relative_path}")
    return resolved_path


def _to_workspace_relative(path: str | Path, workspace_path: Path) -> str:
    return Path(path).resolve().relative_to(workspace_path).as_posix()


def _get_rmbg_model_dir() -> Path:
    if DEFAULT_RMBG_MODEL_DIR.exists():
        return DEFAULT_RMBG_MODEL_DIR.resolve()
    if DEV_RMBG_MODEL_DIR.exists():
        return DEV_RMBG_MODEL_DIR.resolve()
    return DEFAULT_RMBG_MODEL_DIR.resolve()


def _find_icon_infos_for_template(
    workspace_path: Path,
    template_path: Path,
    icon_infos_relative_path: Optional[str],
) -> Path:
    if icon_infos_relative_path:
        return _resolve_relative_path(
            workspace_path,
            icon_infos_relative_path,
            param_name="icon_infos_relative_path",
            must_exist=True,
            must_be_file=True,
        )

    for directory in [template_path.parent, *template_path.parents]:
        candidate = directory / "icon_infos.json"
        if candidate.is_file():
            return candidate
        if directory == workspace_path:
            break

    raise FileNotFoundError(
        "Could not find icon_infos.json. Place it beside the template or pass "
        "icon_infos_relative_path explicitly."
    )


def _infer_template_format(
    template_path: Path,
    output_format: Literal["auto", "drawio", "svg"],
) -> Literal["drawio", "svg"]:
    if output_format != "auto":
        return output_format
    if template_path.suffix.lower() == ".drawio":
        return "drawio"
    if template_path.suffix.lower() == ".svg":
        return "svg"
    raise ValueError("Could not infer output format; template must end with .drawio or .svg")


def _segment_and_extract_icons_sync(
    workspace_dir: str,
    image_path: str,
    sam3_prompt: str,
) -> dict:
    workspace_path = _resolve_workspace(workspace_dir)
    input_image_path = _resolve_relative_path(
        workspace_path,
        image_path,
        param_name="image_path",
        must_exist=True,
        must_be_file=True,
    )
    if input_image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported image suffix: {input_image_path.suffix}")

    output_dir = input_image_path.parent / f"{input_image_path.stem}_output"
    icons_dir = output_dir / "icons"
    icons_nobg_dir = output_dir / "icons_nobg"
    icon_infos_path = output_dir / "icon_infos.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)
    icons_nobg_dir.mkdir(parents=True, exist_ok=True)

    logs = {}

    final_sam3_prompt = f"{sam3_prompt}, icon" if sam3_prompt.strip() else "icon"

    sam3_result, logs["sam3"] = _call_with_logs(
        segment_with_sam3,
        image_path=input_image_path,
        output_dir=output_dir,
        text_prompts=final_sam3_prompt,
    )
    samed_path = Path(sam3_result["samed_path"])
    boxlib_path = Path(sam3_result["boxlib_path"])

    crop_result, logs["crop_icons"] = _call_with_logs(
        crop_icons,
        image_path=input_image_path,
        boxlib_path=boxlib_path,
        output_dir=icons_dir,
    )

    rmbg_result, logs["remove_background"] = _call_with_logs(
        remove_icon_backgrounds,
        model_dir=_get_rmbg_model_dir(),
        icons_dir=icons_dir,
        boxlib_path=boxlib_path,
        output_dir=icons_nobg_dir,
        icon_infos_json=icon_infos_path,
    )

    return {
        "result": "success",
        "output_dir": _to_workspace_relative(output_dir, workspace_path),
        "samed_image": _to_workspace_relative(samed_path, workspace_path),
        "boxlib_json": _to_workspace_relative(boxlib_path, workspace_path),
        "icons_dir": _to_workspace_relative(icons_dir, workspace_path),
        "icons_nobg_dir": _to_workspace_relative(icons_nobg_dir, workspace_path),
        "icon_infos_json": _to_workspace_relative(icon_infos_path, workspace_path),
        "step_results": {
            "sam3": {"box_count": sam3_result.get("box_count")},
            "crop_icons": {"count": crop_result.get("count")},
            "remove_background": {"count": rmbg_result.get("count")},
        },
        "logs": logs,
    }


def _replace_template_placeholders_sync(
    workspace_dir: str,
    template_path: str,
    output_format: Literal["auto", "drawio", "svg"],
    icon_infos_relative_path: Optional[str],
) -> dict:
    workspace_path = _resolve_workspace(workspace_dir)
    template_file = _resolve_relative_path(
        workspace_path,
        template_path,
        param_name="template_path",
        must_exist=True,
        must_be_file=True,
    )
    final_format = _infer_template_format(template_file, output_format)
    icon_infos_path = _find_icon_infos_for_template(
        workspace_path,
        template_file,
        icon_infos_relative_path,
    )
    output_path = template_file.parent / f"final.{final_format}"

    if final_format == "drawio":
        replace_func = replace_drawio_placeholders
        kwargs = {
            "icon_infos_json": icon_infos_path,
            "template_drawio": template_file,
            "output_drawio": output_path,
        }
    else:
        replace_func = replace_svg_placeholders
        kwargs = {
            "icon_infos_json": icon_infos_path,
            "template_svg": template_file,
            "output_svg": output_path,
        }

    replace_result, logs = _call_with_logs(replace_func, **kwargs)
    if not output_path.is_file():
        raise FileNotFoundError(f"Replace step did not create final file: {output_path}")

    return {
        "result": "success",
        "output_format": final_format,
        "final_path": _to_workspace_relative(output_path, workspace_path),
        "template_path": _to_workspace_relative(template_file, workspace_path),
        "icon_infos_json": _to_workspace_relative(icon_infos_path, workspace_path),
        "replace_result": replace_result,
        "logs": logs,
    }


@mcp.tool()
async def segment_and_extract_icons(
    workspace_dir: Annotated[
        str,
        Field(
            description=(
                "Absolute path to the current workspace. "
                "Windows example: D:/mcp_workspace. "
                "Linux/macOS example: /home/user/mcp_workspace."
            )
        ),
    ],
    image_path: Annotated[
        str,
        Field(description="Image path relative to workspace_dir, such as img/demo.png."),
    ],
    sam3_prompt: Annotated[
        str,
        Field(
            description=(
                "Text concept prompt for SAM3/Roboflow detection. "
                "Use comma-separated visual object concepts. "
                "Example: document, computer, clock, person. "
                "For simple object categories, prefer common nouns such as "
                "document, monitor, mask, gear, brain."
            )
        ),
    ],
) -> dict:
    """Run SAM3 segmentation, crop detected icons, and remove icon backgrounds."""
    try:
        return await asyncio.to_thread(
            _segment_and_extract_icons_sync,
            workspace_dir,
            image_path,
            sam3_prompt,
        )
    except Exception as exc:
        return {
            "result": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


@mcp.tool()
async def replace_template_placeholders(
    workspace_dir: Annotated[
        str,
        Field(
            description=(
                "Absolute path to the current workspace. "
                "Windows example: D:/mcp_workspace. "
                "Linux/macOS example: /home/user/mcp_workspace."
            )
        ),
    ],
    template_path: Annotated[
        str,
        Field(
            description=(
                "Template .drawio or .svg path relative to workspace_dir,such as output/template.drawio. "
                "The final file is written beside this template."
            )
        ),
    ],
    output_format: Annotated[
        Literal["auto", "drawio", "svg"],
        Field(description="Use auto to infer from template suffix, or force drawio/svg."),
    ] = "auto",
    icon_infos_relative_path: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional icon_infos.json path relative to workspace_dir,such as output/icon_infos.json. "
                "When omitted, the tool searches template parent directories."
            )
        ),
    ] = None,
) -> dict:
    """Replace draw.io/SVG placeholders with background-removed icon images."""
    try:
        return await asyncio.to_thread(
            _replace_template_placeholders_sync,
            workspace_dir,
            template_path,
            output_format,
            icon_infos_relative_path,
        )
    except Exception as exc:
        return {
            "result": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
