# Draw.io Template Generation

Use this prompt after the MCP tool `segment_and_extract_icons` has succeeded.

Inputs available to you:

- Original image.
- `samed.png` from the MCP tool response.
- `boxlib.json` from the MCP tool response.
- `output_dir` from the MCP tool response.

Your task is to create a draw.io template file at:

`{output_dir}/template.drawio`

`output_dir` is the relative path returned by `segment_and_extract_icons`; create the file under `workspace_dir`.

Do not reply with the full XML in chat unless the user explicitly asks. Write the file in the workspace.

This is `template.drawio`, not `final.drawio`. Do not embed the real cropped icons and do not embed the original raster image. The replacement MCP tool will later replace AF placeholders with transparent PNG icons.

## File Format

Write a complete, uncompressed diagrams.net XML file:

```xml
<mxfile host="app.diagrams.net" modified="..." agent="Edit-Figure-MCP" version="24.7.17" type="device">
  <diagram id="autofigure-template" name="Page-1">
    <mxGraphModel dx="..." dy="..." grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{image_width}" pageHeight="{image_height}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Use `boxlib.json.image_size.width` as `pageWidth` and `boxlib.json.image_size.height` as `pageHeight`. All coordinates must use the original image pixel coordinate system. Do not scale the page or change the aspect ratio.

## AF Placeholder Rules

For every item in `boxlib.json.boxes`, create exactly one independent `mxCell` placeholder.

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

```xml
<mxCell id="AF01"
        value="&amp;lt;AF&amp;gt;01"
        style="rounded=0;whiteSpace=wrap;html=1;fillColor=#808080;strokeColor=#000000;strokeWidth=2;fontColor=#FFFFFF;fontStyle=1;fontSize=32;align=center;verticalAlign=middle;"
        vertex="1"
        parent="1">
  <mxGeometry x="100" y="200" width="200" height="220" as="geometry"/>
</mxCell>
```

Strict requirements:

- `id` is the label with angle brackets removed: `<AF>01` -> `AF01`.
- `value` must be double escaped: `<AF>01` -> `&amp;lt;AF&amp;gt;01`.
- `x = x1`, `y = y1`, `width = x2 - x1`, `height = y2 - y1`.
- Use fill `#808080`, stroke `#000000`, white centered bold label text.
- Do not use a group, child cells, separate text cells, or multiple cells for one placeholder.
- Do not invent extra AF placeholders.
- Do not omit any AF placeholder from `boxlib.json`.
- Use `boxlib.json` coordinates as the source of truth when `samed.png` appears slightly different.

## Reconstruct Editable Content

Use draw.io native cells for the rest of the figure:

- Text as editable text cells.
- Rectangles, rounded rectangles, circles, panels, and backgrounds as vertex cells.
- Arrows and connectors as edge cells.
- Tables, axes, legends, and layout structure as editable primitives when present.

Do not use the original image as a background. Do not use base64 images in the template.

Prioritize:

1. Valid draw.io XML that opens in diagrams.net.
2. Complete and accurate AF placeholders.
3. Main layout, labels, arrows, and grouping.
4. Approximate colors, fonts, shadows, and small decorative details.

Place AF placeholders near the end of the `<root>` so they appear above backgrounds and are not hidden.

After writing `{output_dir}/template.drawio`, use that relative path as `template_path` for `replace_template_placeholders`.
