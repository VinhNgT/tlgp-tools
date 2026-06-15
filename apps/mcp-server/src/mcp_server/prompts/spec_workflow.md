# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Section prefix: **{section_prefix}**

## Language Rule

The user may converse in Vietnamese or English. However, **all content written to the analysis dict** (descriptions, interactions, API titles, field meanings) **must be in Vietnamese**.

## Available Tools

- `launch_annotator` — spawn the Engine and the Annotation GUI for the user
- `get_workspace_state` — fetch the current Flat Map workspace state from the Engine
- `download_image` — download the root screenshot image or a specific component image
- `download_workspace_assets` — download the state and all images in a single batch operation
- `generate_spec_doc` — validate analysis data and generate the .docx

## Source Priority

- **Screenshots** are the source of truth for UI elements and interactions.
- **Source code** is the source of truth for API data and field types.
- When they conflict, **prioritize the image**. Log the conflict in
  `discrepancies` for transparency, but describe the UI based on the screenshot.

---

## Step 1: Annotate

Call `launch_annotator(screenshot_path=...)` if you have a local image to start with, `launch_annotator(workspace_zip=...)` if you have a previously exported .zip workspace, or just `launch_annotator()` if the user will manually import one.
Tell the user: "Please annotate all components, then let me know when done."
Wait for the user to confirm before proceeding.

## Step 2: Analyze & Prepare Workspace

Call `set_workspace_readonly(read_only=True)` to notify the user and lock the workspace in read-only mode during your analysis.

### 2a. Read Annotation State

Call `get_workspace_state()`. This returns the `WorkspaceState` JSON.
Note each component's `id` (a UUID), `label`, and whether it has children in `childrenIds` (non-leaf) or not (leaf).

Download the state and all images in a single batch operation:
1. Call `download_workspace_assets(output_dir="./workspace_xyz")`. This will automatically download and extract `workspace.json`, `raw.png`, and all component images (inside `images/`) into `./workspace_xyz`.
Alternatively, you can call the individual read-only tool:
- `download_image(output_path="./workspace_xyz/raw.png")` to download the root screenshot, or `download_image(comp_id="...", output_path="./workspace_xyz/images/<uuid>.png")` to download a specific component image.

### 2c. Vision analysis

View the annotated screenshots (either provided in the prompt, or by inspecting the UI). For each non-leaf component:

1. Set `description` — Vietnamese description of the component's purpose
2. For each child, set `controlType` using the classification guide below
3. For each child, set `description` — Vietnamese description
4. Set `interactions` — user action / system reaction pairs

Also fill `screen.topLevelChildren` descriptions and `screen.interactions`.

### 2c. Codebase analysis

Search the project code for APIs, DTOs, and navigation routes related to this screen. Fill the `apis` array with endpoint documentation. For POST/PUT/DELETE APIs, set `requestBodyType` to the DTO name.

If the code contradicts the screenshots, log entries in `discrepancies`
but always describe the UI based on what the image shows.

### 2d. Validate & Save

Prepare and validate the analysis data before generating the document.

> [!IMPORTANT]
> **IDE Payload Limitation Bypass**:
> If your `analysis` data is large (e.g. over 10-20KB), the IDE client middleware may corrupt the tool call parameters.
> To bypass this:
> 1. Call `write_analysis_json(data=...)` passing the analysis dictionary. This safely saves it to `analysis.json` inside the export directory and returns the absolute path.
> 2. Pass this path as `analysis_path` to the validation and generation tools.

Call `generate_spec_doc(analysis_path="./workspace_xyz/analysis.json", validate_only=True)`. Fix any issues and re-validate.

## Step 3: Generate

1. Call `generate_spec_doc(analysis_path="./workspace_xyz/analysis.json")`.
2. Call `set_workspace_readonly(read_only=False)` to unlock the workspace and return edit control to the user.

- **If errors:** Fix the analysis dict, save it using `write_analysis_json`, and retry generation.
- **If success:** Report the .docx path and any warnings to the user.
