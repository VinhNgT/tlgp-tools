# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Follow these steps **in order**. Do not skip steps.

## Required References

Before starting, you **must** read these resources:
- **JSON Schema:** `tlgp://spec/schema` — defines the precise structure and validation constraints for `spec.json`.
- **Validation Guide:** `tlgp://spec/validation-guide` — programmatic constraints mapping 1-to-1 to validator errors.
- **Writing & Classification Guide:** `tlgp://spec/writing-guide` — semantic writing rules and UI control type classification rules.
- **Reference Example:** `tlgp://spec/example-analysis` — a complete example spec JSON. Use this as an optional reference for content style.

---

## Workflow Steps

### Step 1: Open the Annotation Tool
- **Goal:** Get the annotator GUI running and connected.
- **Action:**
  - **Option A (New annotator):** Call `launch_annotator(path=...)` with a screenshot image or `.zip` workspace.
  - **Option B (Existing annotator):** Call `connect_to_annotator(url=...)` with the annotator's URL.
- **Stop Condition:** Tell the user to annotate all components in the GUI. **Do not proceed** until the user explicitly confirms they are finished.

### Step 2: Scaffold the Specification
- **Goal:** Export cropped images and auto-generate the structural skeleton of spec.json.
- **Action:** Call `scaffold_spec(output_dir="<directory>")`.
- **Result:** This creates the following outputs in the specified output directory:
  - `spec.json`: The generated structural skeleton of the screen specification with TODO placeholders for semantic details.
  - `schema.json`: The JSON schema validation file for `spec.json`.
  - `mapping.json`: A file mapping component UUIDs to their exported image paths.
  - `raw/`: Subdirectory containing clean, raw cropped images of all annotated components.
  - `annotated/`: Subdirectory containing cropped images of components highlighted with colored borders and red number pills.

### Step 3: Populate Semantic Fields Node-by-Node
- **Goal:** Act strictly as a "fill in the blank" worker. Replace TODO placeholders with real content by cross-referencing both the cropped images and the source code.
- **Action:** For each node ID in the scaffolded tree:
  1. Inspect the component's clean raw crop image (specified by the node's `rawImage` property) to analyze its visual content. Always perform vision analysis on raw crop images to avoid visual noise, colored borders, or text overlays present in annotated crops.
  2. Locate the corresponding Flutter/Dart code implementation to discover interactions and API usages.
  3. Call `update_spec_node` with the specific `node_id` to update `label`, `description`, `control_type`, `interactions` list, and `apis` list according to the **Writing & Classification Guide** (`tlgp://spec/writing-guide`).
- **Discrepancy Handling:** If you find conflicts between what the images show and what the source code shows, you MUST stop and ask the user to clarify. Do not guess.

### Step 4: Iterative Validation Loop
- **Goal:** Validate the spec data, parse errors, and fix them systematically.
- **Action:**
  1. Run `validate_spec(spec_path="<path>")`.
  2. If `valid` is false, read the returned `errors` and `warnings` lists (cross-referencing `tlgp://spec/validation-guide` to resolve structural or unit-limit issues).
  3. Systematically address each error by calling `update_spec_node` on the offending node ID.
  4. Repeat validation and updating iteratively until `validate_spec` returns **zero errors**.

### Step 5: Compile the Specification Document
- **Goal:** Generate the final Word document.
- **Action:** Call `compile_spec(spec_path="<path>", output_path="<docx_path>")`.
- **Result:** This compiles the `.docx` document and automatically exports the verified annotator workspace state as `workspace.zip` next to it for record-keeping.
