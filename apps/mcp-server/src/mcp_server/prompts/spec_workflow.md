# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Follow these steps **in order**. Do not skip steps.

## Rules

1. **Vietnamese Language:** All component labels, UI descriptions, actions, reactions, and discrepancies must be in Vietnamese.
2. **Read-Only Annotator:** You must not mutate the Annotator state directly. All annotation is done by the user in the GUI.
3. **No REST API Bypass:** Do NOT bypass the MCP server layer (e.g. using curl, terminal commands) to interact with the Annotator REST API.
4. **Validation Before Generation:** Always run `generate_spec_doc(validate_only=True)` and resolve all errors before calling with `validate_only=False`.
5. **API Placement:** Document each API under the non-leaf component that **uses** its response data to render/update UI. If an API is used by multiple children, place it on the closest common ancestor. No duplicate APIs allowed.
6. **Vision-Derived Naming:** Component labels and screen names from the workspace are rough suggestions only. Always derive accurate, descriptive Vietnamese labels from the visual content of the cropped images.

## Required References

Before starting, you **must** read these resources:
- **UI Control Types:** `tlgp://spec/classification-guide` — rules for categorizing UI elements.
- **Reference Example:** `tlgp://spec/example-analysis` — a complete example analysis JSON. Use this as your structural template.

## Workflow Steps

### Step 1: Open the Annotation Tool

**Goal:** Get the annotator GUI running and connected.

- **Option A — New annotator:** Call `launch_annotator(path=...)` with a screenshot image or `.zip` workspace.
- **Option B — Existing annotator:** Call `connect_to_annotator(url=...)` with the annotator's URL.

Tell the user to annotate all components in the GUI. **Do not proceed** until the user explicitly confirms they are finished.

### Step 2: Prepare the Analysis

**Goal:** Export images and auto-generate the structural skeleton of analysis.json.

Call `prepare_analysis(output_path="<directory>")`. This single call:
1. Exports cropped component images to the output directory:
   - `annotated/` — images with bounding box overlays (used in the generated document)
   - `raw/` — clean images without overlays (used for your vision analysis)
2. Auto-generates `analysis.json` with:
   - `imageDir` (absolute path to the annotated images directory)
   - `components[]` in post-order DFS with correct `id` sequencing and `isLeaf` flags
   - `imageFile` for each non-leaf component (from mapping.json)
   - `screen.imageFiles` (root annotated images)
   - `screen.topLevelChildren` (from root components)
   - TODO placeholders for all semantic fields

### Step 3: Fill Semantic Fields

**Goal:** Replace TODO placeholders with real content using vision analysis.

Open the scaffolded `analysis.json` file and fill in:

1. **Screen name and description** — derive from the full screenshot
2. **Component labels and descriptions** — inspect the **raw** cropped images (no overlays) and assign descriptive Vietnamese labels based on actual visual content
3. **`topLevelChildren` labels** — must match the labels of the corresponding components in the `components[]` array
4. **`children[]`** for each non-leaf component — categorize visible UI elements using `tlgp://spec/classification-guide`
5. **`interactions[]`** — document user actions and system reactions for non-leaf components
6. **`apis[]`** *(optional, if source code is available)* — document API endpoints, placing each under the component that uses its data
7. **Leaf components** (`isLeaf: true`) — analyze them for context but they have no section in the document. Their `imageFile` is `null`, `children`/`interactions`/`apis` are empty arrays.

### Step 4: Validate & Generate

**Goal:** Validate the payload, fix errors, then generate the .docx file.

1. **Validate:** Call `generate_spec_doc(analysis_path="<path>", validate_only=True)`. Fix any errors in the analysis JSON and re-validate until there are **zero errors**.
2. **Generate:** Call `generate_spec_doc(analysis_path="<path>", validate_only=False)`. This generates the `.docx` and saves `analysis.json` and `workspace.zip` alongside it.
