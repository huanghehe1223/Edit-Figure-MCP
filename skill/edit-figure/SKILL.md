---
name: edit-figure
description: Convert a scientific, technical, or diagrammatic image into an editable draw.io or SVG file using the Edit-Figure-MCP tools. Use when the user asks to convert an image, figure, research diagram, workflow diagram, paper illustration, architecture diagram, or UI-like figure into editable draw.io/diagrams.net XML or SVG; default to draw.io when the target format is not specified.
---

# Edit Figure

Use this skill to convert a raster figure into an editable draw.io or SVG file. The MCP server handles segmentation, icon cropping, background removal, and placeholder replacement. The model handles visual reasoning and writes the editable template file into the workspace.

## Skill Project Layout

File structure:

```text
edit-figure/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
`-- prompts/
    |-- sam3_prompt_generator.md
    |-- template_prompt_drawio.md
    `-- template_prompt_svg.md
```

- `SKILL.md`: main workflow and routing instructions.
- `agents/openai.yaml`: UI-facing skill metadata.
- `prompts/sam3_prompt_generator.md`: guidance for choosing `sam3_prompt`.
- `prompts/template_prompt_drawio.md`: guidance for writing `{output_dir}/template.drawio`.
- `prompts/template_prompt_svg.md`: guidance for writing `{output_dir}/template.svg`.

## Resources

Read only the prompt needed for the current step:

- `prompts/sam3_prompt_generator.md`: plan `sam3_prompt` and call `segment_and_extract_icons`.
- `prompts/template_prompt_drawio.md`: create `{output_dir}/template.drawio`.
- `prompts/template_prompt_svg.md`: create `{output_dir}/template.svg`.

## Workflow

1. Determine the target format.
   - If the user explicitly asks for SVG, produce SVG.
   - If the user asks for both draw.io and SVG, produce both.
   - Otherwise default to draw.io.

2. Plan segmentation.
   - Read `prompts/sam3_prompt_generator.md`.
   - Inspect the original image.
   - Write a brief ordinary-text note: candidate prompts, detect targets, excluded editable elements, reason, and the exact `sam3_prompt` string.
   - Do not require or produce strict JSON for this planning step.

3. Call MCP tool `segment_and_extract_icons`.
   - Required arguments:
     - `workspace_dir`: absolute workspace path.
     - `image_path`: image path relative to `workspace_dir`.
     - `sam3_prompt`: comma-separated prompt string from step 2.
   - Use the returned `output_dir`, `samed_image`, `boxlib_json`, and `icon_infos_json`.
   - `icon_infos.json` is the detailed object record; avoid large per-object chat output.

4. Generate the editable template file in the MCP output directory.
   - For draw.io, read `prompts/template_prompt_drawio.md`.
     - Write directly to `{output_dir}/template.drawio`.
     - Set `template_path` to that relative path.
   - For SVG, read `prompts/template_prompt_svg.md`.
     - Write directly to `{output_dir}/template.svg`.
     - Set `template_path` to that relative path.
   - Use the original image, `samed_image`, and `boxlib_json` as inputs.
   - Preserve the original image coordinate system from `boxlib.json.image_size`.
   - Create every `<AF>xx` placeholder exactly as instructed by the selected template prompt.
   - Do not embed the original raster figure or cropped icons in the template.
   - Do not paste the full template code in chat unless the user explicitly asks; create the file in the workspace.

5. Call MCP tool `replace_template_placeholders`.
   - Required arguments:
     - `workspace_dir`: same absolute workspace path.
     - `template_path`: `{output_dir}/template.drawio` or `{output_dir}/template.svg`, relative to `workspace_dir`.
   - Leave `output_format` as `auto` unless the suffix is ambiguous.
   - Because the template is written beside `icon_infos.json`, `icon_infos_relative_path` is usually unnecessary.
   - The tool writes `final.drawio` or `final.svg` beside the template.

## Output Discipline

- Return the final relative path from the replacement tool.
- Mention the generated `template.*` and `final.*` paths.
- If segmentation finds no icons, still generate the editable template and run replacement.
- If producing both formats, reuse the same segmentation output and run template generation plus replacement once per format.

## Placeholder Rules

- Placeholder IDs must match `boxlib.json` labels after removing angle brackets: `<AF>01` becomes `AF01`.
- The replacement tool depends on those IDs and on `icon_infos.json`.
- Do not invent extra AF placeholders.
- Do not omit AF placeholders found in `boxlib.json`.
- Use draw.io as the default target because it is easier to edit in diagrams.net.
