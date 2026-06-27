# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Follow these steps **in order**. Do not skip steps.

## Rules

1. **Vietnamese Language:** All component labels, UI descriptions, actions, reactions, and discrepancies must be in Vietnamese.
2. **Read-Only Annotator:** You must not mutate the Annotator state directly. All annotation is done by the user in the GUI.
3. **No REST API Bypass:** Do NOT bypass the MCP server layer (e.g. using curl, terminal commands) to interact with the Annotator REST API.
4. **Validation Before Generation:** Always run `generate_spec_doc(validate_only=True)` and resolve all errors before calling with `validate_only=False`.
5. **API Placement:** Document each API under the non-leaf component that **uses** its response data to render/update UI. If an API is used by multiple children, place it on the closest common ancestor. No duplicate APIs allowed.
6. **Vision-Derived Naming:** Component labels and screen names from the workspace are rough suggestions only (shown as `[TODO: ... Suggestion: X]` in the scaffold). Always derive accurate, descriptive Vietnamese labels from the visual content of the cropped images.
7. **Unit Limit:** Each component and the screen have a complexity budget (default: 15 units; 1 unit per annotation, 3 per API). Validation will reject any scope that exceeds its limit. You MUST NOT attempt to resolve this yourself (e.g. by restructuring the analysis, removing children, or moving APIs). Instead, stop and ask the user to re-annotate the image in the Annotation Tool — for example, by grouping child elements under a new parent component to reduce the count at the offending level. After the user re-annotates, re-run `prepare_analysis` to regenerate the scaffold. The limits are configurable via the `unitLimit` field in analysis.json.
8. **Source Code Discovery:** When mapping components, interactions, and APIs to the source code, you must locate the corresponding source code elements (such as components, widgets, or controllers). If you cannot resolve or locate the matching source code files, you **must stop and ask the user** for help rather than guessing or making assumptions.
9. **High-Level Descriptions (Summary):** When writing the "description" for a screen (`screen.description`) or a component (`component.description`), write a true high-level summary (Mô tả) of its function/purpose. Do NOT simply re-state or list the UI elements or children inside it, as those are already detailed in the "Mô tả chi tiết các thành phần trên màn hình" (UI elements) table.

## Required References

Before starting, you **must** read these resources:
- **JSON Schema:** `tlgp://spec/schema` — defines the precise structure and validation constraints for `analysis.json`.
- **UI Control Types:** `tlgp://spec/classification-guide` — rules for categorizing UI elements.
- **Reference Example:** `tlgp://spec/example-analysis` — a complete example analysis JSON. Use this as an optional reference for content style.

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
   - `imageDir` (absolute path to the export root directory)
   - `components[]` in post-order DFS with correct `id` sequencing and `isLeaf` flags
   - `imageFile` for each non-leaf component (prefixed with `annotated/`)
   - `screen.imageFiles` (root annotated images, prefixed with `annotated/`)
   - `screen.topLevelChildren` (pre-populated using componentId mapping)
   - TODO placeholders (with suggestions where available) for all semantic fields

### Step 3: Fill Semantic Fields

**Goal:** Replace TODO placeholders with real content by cross-referencing **both** the cropped images **and** the source code in parallel.

Open the scaffolded `analysis.json` file and fill in:

1. **Screen name and description** — replace the suggestion placeholders in `screen.name` and `screen.description` with real Vietnamese values derived from the full screenshot and corresponding screen code. Write `screen.description` as a true high-level summary (mô tả chung) of the screen's role/purpose, NOT a list or restatement of its UI elements (since we have the UI elements/children table for that).
2. **Component labels and descriptions** — replace the label suggestion placeholders in the `components[]` array with accurate, descriptive Vietnamese labels. Write the component description as a true high-level summary (mô tả chung) of its role/purpose, NOT simply re-stating the UI elements or children inside it (since we have the UI elements/children table for that).
3. **Top-level and Nested component references** — `screen.topLevelChildren` and nested component children are automatically mapped to components in the scaffold using `componentId`. You **do NOT need to write or sync labels or descriptions manually** for these referenced components (they resolve dynamically during parsing). Only populate/override fields like `required` or `maxLength` if needed, otherwise keep them empty.
4. **`children[]`** for each non-leaf component — the scaffold automatically populates nested child components via `componentId`. For *unannotated* leaf UI elements (e.g., Buttons, Icons, Text fields) visible in the cropped images, you must manually append them to this array, assigning correct `stt` sequencing, `label`, `controlType`, and `description` according to `tlgp://spec/classification-guide`.
5. **`interactions[]`** — derive user actions and system reactions from both the visual behavior shown in images and the event handlers/logic in the source code.
6. **`apis[]`** *(optional, if source code is available)* — document API endpoints, placing each under the component that uses its data.
7. **Leaf components** (`isLeaf: true`) — analyze them for context but they have no section in the document. Their `imageFile` is `null`, `children`/`interactions`/`apis` are empty arrays.

**Discrepancy Handling:** If you find conflicts between what the images show and what the source code shows (e.g., a button visible in the screenshot but absent in the code, or a field present in code but hidden in the UI), you MUST stop and ask the user to clarify. The user will either: (a) explain the correct behavior — update the analysis accordingly, or (b) confirm it is a genuine discrepancy — record it in the `discrepancies[]` array with both observations.

### Step 4: Validate & Generate

**Goal:** Validate the payload, fix errors, then generate the .docx file.

1. **Validate:** Call `generate_spec_doc(analysis_path="<path>", validate_only=True)`. Fix any errors in the analysis JSON and re-validate until there are **zero errors**.
2. **Generate:** Call `generate_spec_doc(analysis_path="<path>", validate_only=False)`. This generates the `.docx` and saves `analysis.json` and `workspace.zip` alongside it.
