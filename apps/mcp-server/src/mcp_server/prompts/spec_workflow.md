# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Follow these steps **in order**. Do not skip steps.

## Strict Guidelines

{strict_guidelines}

## Required Guides & Resources

Before starting, you **must** read these resources:
- **UI Control Types:** `tlgp://spec/classification-guide` — rules for categorizing UI elements.
- **JSON Schema:** `tlgp://spec/schema` — the structure of the analysis JSON payload.
- **Reference Example:** `tlgp://spec/example-analysis` — a complete example analysis JSON.

## Workflow Steps

### Step 1: Open the Annotation Tool

**Goal:** Get the annotator GUI running and connected.

Choose **one** of these options:

- **Option A — Launch a new annotator:** Call `launch_annotator(path=...)` with a screenshot image or `.zip` workspace, or `launch_annotator()` to let the user load one manually.
- **Option B — Connect to an already-running annotator:** If the user has already started the annotator (e.g., from the terminal), call `connect_to_annotator(url=...)` with the annotator's URL (default: `http://127.0.0.1:8000`). Ask the user for the URL if you do not know it.

After connecting, tell the user to annotate all components in the GUI.

### Step 2: Wait for User to Finish

**Goal:** Wait until the user has finished annotating.

Tell the user: *"Let me know when you're done annotating."*

**Do not proceed to Step 3** until the user explicitly confirms they are finished (e.g., "done", "finished", "ready"). Once confirmed, proceed immediately to Step 3.

### Step 3: Retrieve Annotation State & Export Images

**Goal:** Get the component hierarchy and export cropped images.

1. **Read the workspace state:** Read the resource `tlgp://workspace/state`. This gives you the full component hierarchy with IDs, labels, and parent-child relationships.
2. **Export images:** Call `export_images(output_path="<directory>")`. Choose a directory path for the exported images. This tool returns:
   - `output_path` — the directory where images were saved
   - `root_images` — list of filenames of the full screenshot segments (**save these — you need them in Step 4**)
   
   The export creates two subdirectories:
   - `annotated/` — images with bounding box overlays (use these as `imageFile` references in the analysis JSON for the generated document)
   - `raw/` — clean images without overlays (use these for your own visual analysis)

### Step 4: Analyze & Build the Analysis JSON

**Goal:** Construct the complete analysis JSON payload and save it to disk.

1. **Ask the user for the `sectionPrefix`** — this is the section number prefix used for component headings in the generated document (e.g., `"1.1"`, `"2.3"`). If the user does not specify one, default to `"1.1"`.

2. **Vision analysis:** Inspect the **raw** component images (from the `raw/` subdirectory — no overlays, optimal for visual analysis). For each component:
   - Categorize its child elements using the rules in `tlgp://spec/classification-guide`
   - Write all labels, descriptions, actions, and reactions in **Vietnamese**
   - Set `imageFile` to the component's **annotated** image filename (from `annotated/`)
   - Set `screen.imageFiles` to the exact `root_images` list returned by `export_images` in Step 3

3. **Codebase analysis** *(optional — only if you have access to the project source code):* Search the codebase for APIs, DTOs, and navigation routes related to the screen. Fill in the `apis` list for each component and the screen. Place each API under the component that **uses** its data (see Guideline 10). Log any conflicts in `discrepancies`.

4. **Save the analysis JSON to disk:** Write the complete JSON payload to a file at `<output_path>/analysis.json` (where `output_path` is the image directory from Step 3). You **must** save the file before proceeding — the next step reads from this file path.

### Step 5: Validate & Generate the Document

**Goal:** Validate the payload, fix errors, then generate the `.docx` file.

1. **Validate first:** Call `generate_spec_doc(analysis_path="<path_to_analysis.json>", validate_only=True)`. Review the returned `warnings` and `errors`. If there are errors, fix your analysis JSON file, save it again, and re-validate until there are **zero errors**.
2. **Generate:** Call `generate_spec_doc(analysis_path="<path_to_analysis.json>", validate_only=False)`. This generates the `.docx` document and automatically saves the final `analysis.json` and `workspace.zip` next to it for record-keeping.

*(Note: The document builder organizes the DOCX by sections: non-leaf components in DFS order first, then the screen overview section. Each section appends its own API documentation at the end.)*
