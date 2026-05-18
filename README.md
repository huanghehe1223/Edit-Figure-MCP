# Edit-Figure-MCP

An MCP server for converting a scientific/technical figure into editable
draw.io or SVG output.

The project keeps the MCP server thin and puts reusable processing logic in the
`edit_figure/` package:

- `sam3_segmenter.py`: SAM3/Roboflow concept detection, writes `samed.png` and `boxlib.json`.
- `icon_cropper.py`: crops detected icon regions into `icons/`.
- `background_remover.py`: runs RMBG-2.0 and writes `icons_nobg/` plus `icon_infos.json`.
- `drawio_placeholder_replacer.py`: replaces draw.io placeholder cells with icon images.
- `svg_placeholder_replacer.py`: replaces SVG placeholder groups/rects with icon images.

The companion Codex skill lives in `skill/edit-figure/` and contains:

- `SKILL.md`
- `prompts/sam3_prompt_generator.md`
- `prompts/template_prompt_drawio.md`
- `prompts/template_prompt_svg.md`
- `agents/openai.yaml`

## Tools

- `segment_and_extract_icons`
  - Inputs: `workspace_dir`, `image_path`, `sam3_prompt`
  - Writes outputs beside the input image in `{image_stem}_output/`.

- `replace_template_placeholders`
  - Inputs: `workspace_dir`, `template_path`
  - Optional: `output_format`, `icon_infos_relative_path`
  - Infers draw.io/SVG from the template suffix when `output_format` is `auto`.
  - Writes `final.drawio` or `final.svg` beside the template.

## Expected Workflow

1. The model reads the skill prompt for SAM3 prompt generation.
2. The model inspects the original image and calls `segment_and_extract_icons`.
3. The model reads the draw.io or SVG template prompt, the original image,
   `samed.png`, and `boxlib.json`, then writes `template.drawio` or `template.svg`
   into the output directory.
4. The model calls `replace_template_placeholders`.

When the user does not specify a target format, prefer draw.io.

## Run

Install dependencies in the Python environment that has the required models:

```powershell
pip install -r Edit-Figure-MCP/requirements.txt
```

Start the MCP server over stdio:

```powershell
python Edit-Figure-MCP/edit_figure_mcp_server.py
```

`RMBG_MODEL_DIR` can be set to the local RMBG-2.0 model directory. By default,
the server looks for `Edit-Figure-MCP/models/RMBG-2.0`, and also supports the
original repo layout during development.
