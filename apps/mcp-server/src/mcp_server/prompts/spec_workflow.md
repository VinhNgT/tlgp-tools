# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
The `sectionPrefix` field (e.g. "1.1") is configured in the analysis JSON payload.

## Strict Guidelines

{strict_guidelines}

## Required Guides & Resources

Before starting, read these resources to understand the component classifications and JSON structure:
- **UI Control Types:** Read the classification rules at `tlgp://spec/classification-guide`.
- **JSON Schema:** Read the schema specification reference at `tlgp://spec/schema`.
- **Reference Example:** Inspect the complete example analysis structure at `tlgp://spec/example-analysis`.

## High-Level Workflow Steps

### Step 1: Annotate
1. Call `launch_annotator(path=...)` if you have a local image or a previously exported .zip workspace to start with, or just `launch_annotator()` if the user will manually import one.
2. Direct the user to annotate all components in the GUI and wait for them to confirm when finished.

### Step 2: Retrieve Annotation State & Assets
1. Retrieve the active annotation hierarchy state: read the resource `tlgp://workspace/state`.
2. Export cropped component image assets: call `export_images(output_path="<your_chosen_image_dir>")`. This extracts both raw crops (clean, for AI vision analysis, under `raw/`) and annotated crops (with bounding box overlays, for document compilation, under `annotated/`) into the target directory. The `output_path` you choose here will be used as the `imageDir` in the analysis JSON.

### Step 3: Analyze
1. **Vision analysis:** Inspect the raw component images (the clean crops under `raw/` without bounding box overlays, which are optimal for AI vision models) from the export directory. Categorize components using the rules in `tlgp://spec/classification-guide`. Fill in component details, child control types, descriptions, and interactions.
2. **Codebase analysis:** Search the codebase for APIs, DTOs, and navigation routes related to the screen. Fill in the APIs list in each component and the screen. Be careful to place the API under the component that **uses** the API (displays its data or handles its response), not where it is called in code (such as screen controllers or coordinators). If an API is shared/used by multiple child components, place it in the closest common parent component (or the screen overview) that encompasses all of them to avoid duplication. Ensure no duplicate APIs are defined (each API must have a unique sequential number and unique method/url endpoint, belonging to exactly one component or screen). See Guideline 10. Log any conflicts between code and screenshots in `discrepancies`.
3. **Guidance on mismatch:** You must always cross-reference the screenshot and components in the workspace with the target codebase. If the screenshot or components do not match the target codebase, you MUST stop and ask the user for guidance.


### Step 4: Validate & Generate
1. **Validate:** Run `generate_spec_doc(analysis_path=..., validate_only=True)`. Fix any warnings or errors returned.
2. **Generate:** Run `generate_spec_doc(analysis_path=..., validate_only=False)`. This will generate the `.docx` document and automatically save/copy the final `analysis.json` and `workspace.zip` next to the `.docx` file for record-keeping.
   *(Note: The document builder organizes the DOCX file by sections: first the non-leaf components (in DFS order), and then the screen overview section. Each component and screen section appends its own API documentation at the end.)*
