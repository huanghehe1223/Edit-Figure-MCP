# SVG Template Generation

Use this prompt after the MCP tool `segment_and_extract_icons` has succeeded.

Inputs available to you:

- Original image.
- `samed.png` from the MCP tool response.
- `boxlib.json` from the MCP tool response.
- `output_dir` from the MCP tool response.

Your task is to create an SVG template file at:

`{output_dir}/template.svg`

`output_dir` is the relative path returned by `segment_and_extract_icons`; create the file under `workspace_dir`.

Do not reply with the full SVG in chat unless the user explicitly asks. Write the file in the workspace.

This is `template.svg`, not `final.svg`. Do not embed the real cropped icons and do not embed the original raster image. The replacement MCP tool will later replace AF placeholders with transparent PNG icons.

## SVG Size

Use `boxlib.json.image_size`:

- `width="{image_size.width}"`
- `height="{image_size.height}"`
- `viewBox="0 0 {image_size.width} {image_size.height}"`

All coordinates must use the original image pixel coordinate system. Do not scale the page or change the aspect ratio.

## AF Placeholder Rules

For every item in `boxlib.json.boxes`, create exactly one placeholder group.

Given:

```json
{
  "label": "<AF>01",
  "x1": 100,
  "y1": 200,
  "x2": 300,
  "y2": 420
}
```

Create:

```svg
<g id="AF01">
  <rect x="100" y="200" width="200" height="220" fill="#808080" stroke="#000000" stroke-width="2"/>
  <text x="200" y="310" text-anchor="middle" dominant-baseline="middle" fill="#FFFFFF" font-size="32" font-weight="700">&lt;AF&gt;01</text>
</g>
```

Strict requirements:

- `id` is the label with angle brackets removed: `<AF>01` -> `AF01`.
- Text must escape angle brackets: `&lt;AF&gt;01`.
- `x = x1`, `y = y1`, `width = x2 - x1`, `height = y2 - y1`.
- Use gray fill `#808080`, black stroke, white centered label text.
- Do not invent extra AF placeholders.
- Do not omit any AF placeholder from `boxlib.json`.
- Use `boxlib.json` coordinates as the source of truth when `samed.png` appears slightly different.

## Reconstruct Editable Content

Use SVG primitives for the rest of the figure:

- `<text>` for titles, labels, and annotations.
- `<rect>`, `<circle>`, `<ellipse>`, `<path>`, `<line>`, and `<polygon>` for editable shapes.
- `<defs>` for markers, gradients, clipping, filters, and arrowheads when useful.
- `<path>` or `<line>` with markers for arrows and connectors.

Do not embed the original image. Do not embed cropped icons. Do not use external image links. Do not use JavaScript.

Prioritize:

1. Valid SVG XML.
2. Complete and accurate AF placeholders.
3. Main layout, labels, arrows, and grouping.
4. Approximate colors, fonts, shadows, and small decorative details.

Place AF placeholder groups near the end of the SVG so they appear above backgrounds and are not hidden.

After writing `{output_dir}/template.svg`, use that relative path as `template_path` for `replace_template_placeholders`.
