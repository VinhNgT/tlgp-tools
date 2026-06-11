"""MCP prompt — step-by-step workflow for creating a spec document.

The agent's core job is filling in the analysis.json template with
vision + codebase data, then generating the final .docx.
"""

SPEC_WORKFLOW_PROMPT = """\
# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Section prefix: **{section_prefix}**

## Available Tools

- `launch_annotator` — open the annotation GUI for the user
- `prepare_analysis` — discover exports, scaffold analysis.json, return docs
- `update_analysis` — patch fields in analysis.json by path
- `finalize` — validate and generate the .docx

## Source Priority

- **Screenshots** are the source of truth for UI elements and interactions.
- **Source code** is the source of truth for API data and field types.
- When they conflict, add the conflict to the `discrepancies` array.

---

## Step 1: Prepare

Call `prepare_analysis(output_dir=..., section_prefix="{section_prefix}")`.

**If status is "needs_annotation":**
1. Call `launch_annotator` with screenshot paths and output_dir.
2. Tell the user: "Please annotate all components, then let me know when done."
3. Wait for the user to confirm, then call `prepare_analysis` again.

**If status is "complete":** Ask the user if they want to regenerate.

**Otherwise:** Note the `analysis_path` and review the `components` list. \
The response includes `schema` (field reference) and `control_types` \
(classification guide) — use these in Step 2.

## Step 2: Vision Analysis

View each image from `image_files` and each component's `imageFile`.

For each non-leaf component, call `update_analysis` with:

```json
[
  {{"path": "components[N].description", "value": "Vietnamese description"}},
  {{"path": "components[N].children[M].controlType", "value": "Button"}},
  {{"path": "components[N].children[M].description", "value": "Vietnamese description"}},
  {{"path": "components[N].interactions", "value": [
    {{"action": "Click vào nút X", "reaction": "Hệ thống thực hiện Y"}}
  ]}}
]
```

Valid controlType values: Button, Text, Icon, Image, Component, \
TextField, Checkbox, Switch, Tabbar, Slide.

Also fill `screen.interactions` and screen `topLevelChildren` descriptions.

Write all descriptions in Vietnamese.

## Step 3: Codebase Analysis

Search the project code for APIs, DTOs, and navigation routes related \
to this screen. Call `update_analysis` with:

```json
[
  {{"path": "apis", "value": [
    {{
      "number": 1,
      "method": "GET",
      "title": "Vietnamese title",
      "url": "/api/endpoint",
      "requestParams": [{{"name": "field", "meaning": "...", "required": "Có", "dataType": "String", "limit": "", "defaultValue": ""}}],
      "requestBodyType": "",
      "responseType": "DtoName",
      "responseFields": [...],
      "subDtos": [...]
    }}
  ]}},
  {{"path": "discrepancies", "value": [
    {{"location": "Component Name", "imageObservation": "...", "codeObservation": "..."}}
  ]}}
]
```

For POST/PUT/DELETE APIs, set `requestBodyType` to the DTO name \
(renders as "Request Body (DtoName)" in the document).

## Step 4: Finalize

Call `finalize(json_path=...)`.

- **If errors:** Fix with `update_analysis` and call `finalize` again.
- **If success:** Report the .docx path and any warnings to the user.
"""
