# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Section prefix: **{section_prefix}**

## Strict Guidelines

{strict_guidelines}

## Required Guides & Resources

Before starting, read these resources to understand the component classifications and JSON structure:
- **UI Control Types:** Read the classification rules at `tlgp://spec/classification-guide`.
- **JSON Schema:** Read the schema specification reference at `tlgp://spec/schema`.
- **Reference Example:** Inspect the complete example analysis structure at `tlgp://spec/example-analysis`.

## High-Level Workflow Steps

### Step 1: Annotate
1. Call `launch_annotator(screenshot_path=...)` if you have a local image to start with, `launch_annotator(workspace_zip=...)` if you have a previously exported workspace, or just `launch_annotator()` if the user will manually import one.
2. Direct the user to annotate all components in the GUI and wait for them to confirm when finished.

### Step 2: Retrieve Annotation State & Assets
1. Set the workspace to read-only during analysis: call `set_workspace_readonly(read_only=True)`.
2. Retrieve the active annotation hierarchy state: read the resource `tlgp://workspace/state`.
3. Download unannotated image assets for vision analysis: call `download_workspace_assets(output_dir="./unannotated_assets", show_root_children=False, show_component_children=False)`. You MUST use these unannotated images for AI vision analysis so that bounding box overlays do not obscure UI details.
4. Download annotated image assets for document generation: call `download_workspace_assets(output_dir="./workspace_xyz", show_root_children=True, show_component_children=True)`. These annotated images (with bounding box overlays and ID labels) must be used in `analysis.json` and embedded in the generated DOCX so the reader can cross-reference with the component tables.

### Step 3: Analyze
1. **Vision analysis:** Inspect the screenshot and component images from the `./unannotated_assets` directory. Categorize components using the rules in `tlgp://spec/classification-guide`. Fill in component details, child control types, descriptions, and interactions.
2. **Codebase analysis:** Search the codebase for APIs, DTOs, and navigation routes related to the screen. Fill in the APIs list. Log any conflicts between code and screenshots in `discrepancies`.

### Step 4: Validate & Generate
1. **IDE Parameter Bypass:** If the analysis data is large (e.g., >10KB), you MUST call `write_analysis_json(data=...)` to save it to disk and retrieve the file path. Pass this path as `analysis_path` to `generate_spec_doc`.
2. **Validate:** Run `generate_spec_doc(analysis_path=..., validate_only=True)`. Fix any warnings or errors returned.
3. **Generate:** Run `generate_spec_doc(analysis_path=..., validate_only=False)`. This will generate the `.docx` document and automatically save/copy the final `analysis.json` next to the `.docx` file for record-keeping.
   *(Note: The document builder organizes the DOCX file in the following order: (1) Component sections (DFS order), (2) Screen overview section (containing the root/main screen image), and (3) API documentation.)*
4. **Unlock Workspace:** Call `set_workspace_readonly(read_only=False)` to return edit control to the user.
