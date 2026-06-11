"""MCP prompt — step-by-step workflow for creating a spec document.

The agent's core job is filling in the analysis.json template with
vision + codebase data, then generating the final .docx.
"""

SPEC_WORKFLOW_PROMPT = """\
# TLGP Screen Specification Document Workflow

You are creating a detailed specification document for a mobile app screen.
Section prefix: **{section_prefix}**

## Available Tools

- `launch_annotator` — spawn the annotation GUI
- `list_exports` — inspect directory state
- `parse_annotations` — read annotation JSON
- `scaffold_analysis` — auto-generate analysis.json template
- `validate_analysis` — check analysis.json
- `generate_docx` — produce the .docx

## Available Resources

- `tlgp://schema/analysis-json` — field reference for analysis.json
- `tlgp://schema/control-types` — UI control classification guide
- `tlgp://spec/formatting` — formatting config (read-only)

---

## Step 1: Check Workspace

Call `list_exports` with the output directory.

Based on the status:
- **not_found** / **empty**: Proceed to Step 2.
- **annotations_only**: Skip to Step 3.
- **ready**: Skip to Step 6.
- **complete**: Ask the user if they want to regenerate.
- **malformed**: Report the issues and ask how to proceed.

## Step 2: Launch Annotator

Call `launch_annotator` with the screenshot paths and output directory.

Tell the user:
> "The annotation tool is open. Please annotate all UI components \
on the screen, then click Export (Ctrl+S). Let me know when you're done."

**Wait for the user to confirm they've finished annotating.**

## Step 3: Parse & Scaffold

1. Call `list_exports` to discover the exported files.
2. Call `parse_annotations` with the annotation JSON path.
3. Call `scaffold_analysis` to generate the analysis.json template.
4. Read the `tlgp://schema/analysis-json` resource for field reference.
5. Read the `tlgp://schema/control-types` resource for classification guide.

## Step 4: Vision Analysis

View each annotated image (use your vision capabilities) and for each \
component's children:

1. Identify the control type (Button, Text, Icon, Image, Component, \
TextField, Checkbox, Switch, Tabbar, Slide).
2. Determine if the element is required/editable.
3. Write a concise Vietnamese description.
4. Identify interaction patterns (user action → system reaction).

Update the analysis.json with your findings.

## Step 5: Codebase Analysis

Search the project codebase for:

1. **API endpoints** related to this screen:
   - Search for route definitions, Retrofit/Dio service methods.
   - Document method, URL, request params, response fields.
2. **DTOs and models**:
   - Find request/response DTOs.
   - Document every field: name, type, required, constraints.
3. **Navigation routes**:
   - Find how this screen is reached and where it navigates to.

Fill in the `apis` section and interaction reactions with codebase evidence.

## Step 6: Validate

Call `validate_analysis` with the analysis.json path.

- If **errors**: fix them and re-validate.
- If **warnings**: review them — fill in missing descriptions, \
control types, or APIs if needed.
- If **valid with no warnings**: proceed.

## Step 7: Generate

Call `generate_docx` with the analysis.json path.

Report the result to the user:
> "Generated specification document: [filename] \
(X tables, Y images). The file is at: [path]"

---

## Important Notes

- Always write descriptions in Vietnamese.
- Default actor is "Người dùng" (App User). Change if the screen \
is for a different actor (e.g., admin, merchant).
- Each component's `imageFile` points to the cropped annotated \
image — verify these exist before generating.
- If the annotation tool was not installed or cannot be launched, \
ask the user to install it: `uv pip install tlgp-annotation-tool`
"""
