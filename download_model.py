"""
只下载 BRIA RMBG-2.0 的 model.safetensors 到本地。

适用场景：
- 其它模型配置文件已经通过 git 跟踪并同步
- 只需要在新设备上补下载大文件 model.safetensors
"""

# /usr/bin/python3 -s /kaggle/working/Edit-Figure-MCP/edit_figure_mcp_server.py
import os
from pathlib import Path

from huggingface_hub import hf_hub_download


MODEL_REPO_ID = "briaai/RMBG-2.0"
LOCAL_MODEL_DIR = "models/RMBG-2.0"
MODEL_FILENAME = "model.safetensors"


def main() -> None:
    token = ""

    if not token:
        raise RuntimeError(
            "未检测到 HF_TOKEN 环境变量。\n"
            "请先设置 HuggingFace token，例如：\n"
            "  macOS/Linux: export HF_TOKEN=你的token\n"
            "  Windows PowerShell: $env:HF_TOKEN='你的token'"
        )

    local_dir = Path(LOCAL_MODEL_DIR)
    local_dir.mkdir(parents=True, exist_ok=True)

    target_file = local_dir / MODEL_FILENAME

    if target_file.exists():
        print(f"{MODEL_FILENAME} 已存在，跳过下载。")
        print(f"文件位置: {target_file.resolve()}")
        return

    print(f"开始下载: {MODEL_REPO_ID}/{MODEL_FILENAME}")
    print(f"保存目录: {local_dir.resolve()}")

    downloaded_path = hf_hub_download(
        repo_id=MODEL_REPO_ID,
        filename=MODEL_FILENAME,
        token=token,
        local_dir=str(local_dir),
    )

    print("\n下载完成。")
    print(f"文件位置: {Path(downloaded_path).resolve()}")


main()