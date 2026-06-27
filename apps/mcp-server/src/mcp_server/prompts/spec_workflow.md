# TLGP Screen Specification Workflow

You are creating a specification document for a mobile app screen.
Follow these steps **in order**. Do not skip steps.

## Rules

1. **Vietnamese Language:** All component labels, UI descriptions, actions, reactions, and discrepancies must be in Vietnamese.
2. **Read-Only Annotator:** You must not mutate the Annotator state directly. All annotation is done by the user in the GUI.
3. **No REST API Bypass:** Do NOT bypass the MCP server layer (e.g. using curl, terminal commands) to interact with the Annotator REST API.
4. **Validation Before Generation:** Always run `generate_spec_doc(validate_only=True)` and resolve all errors before calling with `validate_only=False`.
5. **API Placement:** Document each API under the non-leaf component that **uses** its response data to render/update UI. If an API is used by multiple children, place it on the closest common ancestor. No duplicate APIs allowed.
6. **Vision-Derived Naming & No Prefixes:** Component labels and screen names from the workspace are rough suggestions only (shown as `[TODO: ... Suggestion: X]` in the scaffold). Always derive accurate, descriptive Vietnamese labels from the visual content of the cropped images. Do NOT include generic prefixes such as "Màn hình", "Trang", "Screen", "Page", "Component", or "Thành phần" in the screen node or component node `label` (e.g. write "Cài đặt" instead of "Màn hình Cài đặt" or "Trang Cài đặt"). The document compiler automatically prepends the correct prefix ("Màn hình " or "Component ") during generation.
7. **Unit Limit:** Each component and the screen have a strict, non-configurable complexity budget of 15 units (1 unit per annotation, 3 per API). Validation will reject any scope that exceeds this limit. You MUST NOT attempt to resolve this yourself (e.g. by restructuring the analysis, removing children, moving APIs, or editing any configuration). Under no circumstances should you omit any required APIs or compromise on documentation depth to avoid this limit. If documenting all used APIs would cause the screen or any component to exceed the 15-unit limit, you MUST immediately stop and ask the user to re-annotate the image in the Annotation Tool (for example, by grouping child elements under a new parent component to reduce the count at the offending level). After the user re-annotates, re-run `prepare_analysis` to regenerate the scaffold.
8. **Source Code Discovery:** When mapping components, interactions, and APIs to the source code, you must locate the corresponding source code elements (such as components, widgets, or controllers). If you cannot resolve or locate the matching source code files, you **must stop and ask the user** for help rather than guessing or making assumptions.
9. **High-Level Descriptions (Summary):** When writing the "description" for a node (`node.description`), write a true high-level summary (Mô tả) of its function/purpose. Do NOT simply re-state or list the UI elements or children inside it, as those are already detailed in the "Mô tả chi tiết các thành phần trên màn hình" (UI elements) table.
10. **Strict "Fill in the Blank" Operation:** The AI must solely "fill in the blank" created by the pre-analysis step. For the visual UI structure (`nodes` and `childrenIds`), you must solely fill in the `[TODO: ...]` blanks without altering the tree relationships. You are strictly forbidden from modifying the structural tree relationships (adding or removing nodes from the list or changing `childrenIds`). However, you ARE expected to append items to the empty `interactions[]` and `apis[]` arrays based on your source code analysis.

## Required References

Before starting, you **must** read these resources:
- **JSON Schema:** `tlgp://spec/schema` — defines the precise structure and validation constraints for `spec.json`.
- **UI Control Types:** `tlgp://spec/classification-guide` — rules for categorizing UI elements.
- **Reference Example:** `tlgp://spec/example-analysis` — a complete example spec JSON. Use this as an optional reference for content style.

## Workflow Steps

### Step 1: Open the Annotation Tool

**Goal:** Get the annotator GUI running and connected.

- **Option A — New annotator:** Call `launch_annotator(path=...)` with a screenshot image or `.zip` workspace.
- **Option B — Existing annotator:** Call `connect_to_annotator(url=...)` with the annotator's URL.

Tell the user to annotate all components in the GUI. **Do not proceed** until the user explicitly confirms they are finished.

### Step 2: Prepare the Specification

**Goal:** Export images and auto-generate the structural skeleton of spec.json.

Call `prepare_analysis(output_path="<directory>")`. This single call:
1. Exports cropped component images to the output directory:
   - `annotated/` — images with bounding box overlays (used in the generated document)
   - `raw/` — clean images without overlays (used for your vision analysis)
2. Auto-generates `spec.json` with:
   - `imageDir` (absolute path to the export root directory)
   - `rootId` (always `"0"`, representing the screen)
   - `nodes[]` — a flat list of `NodeSpec`s including the screen (ID `"0"`) and all annotated components (keyed by their workspace UUIDs)
   - `imageFiles` for the screen and non-leaf components
   - `childrenIds` listing the child node IDs for each parent
   - TODO placeholders (with suggestions where available) for all semantic fields

### Step 3: Fill Semantic Fields

**Goal:** Act strictly as a "fill in the blank" worker. Replace TODO placeholders with real content by cross-referencing **both** the cropped images **and** the source code in parallel. Do not alter the generated UI structure arrays.

Open the scaffolded `spec.json` file and fill in:

1. **Screen node (ID "0") label and description** — replace the suggestion placeholders in `label` and `description` with real Vietnamese values derived from the full screenshot and corresponding screen code. Write the label without any generic prefixes (e.g. write "Cài đặt" instead of "Màn hình Cài đặt"). Write `description` as a true high-level summary (mô tả chung) of the screen's role/purpose, NOT a list or restatement of its UI elements (since we have the UI elements/children table for that).
2. **Component labels and descriptions** — replace the label suggestion placeholders in the `nodes[]` list with accurate, descriptive Vietnamese labels without any generic prefixes (e.g. write "Header" instead of "Component Header"). Write the component description as a true high-level summary (mô tả chung) of its role/purpose, NOT simply re-stating the UI elements or children inside it (since we have the UI elements/children table for that).
3. **`interactions[]`** — derive user actions and system reactions from both the visual behavior shown in images and the event handlers/logic in the source code.
4. **`apis[]`** *(optional, if source code is available)* — document API endpoints, placing each under the component that uses its data.
5. **Leaf nodes (elements)** — if a node has no children (`childrenIds: []`), it is a leaf element. Fill in the `controlType` with a valid widget type (e.g. `Button`, `Text`, `Icon`, `Image`) and optional validation properties (`required`, `maxLength`, `editable`). Leaf elements do not generate separate sections or image embeds in the document.

**Discrepancy Handling:** If you find conflicts between what the images show and what the source code shows (e.g., a button visible in the screenshot but absent in the code, or a field present in code but hidden in the UI), you MUST stop and ask the user to clarify. The user will either: (a) explain the correct behavior — update the spec accordingly, or (b) confirm it is a genuine discrepancy — record it in the `discrepancies[]` array with both observations.

### Step 4: Validate & Generate

**Goal:** Validate the payload, fix errors, then generate the .docx file.

1. **Validate:** Call `generate_spec_doc(spec_path="<path>", validate_only=True)`. Fix any errors in the `spec.json` and re-validate until there are **zero errors**.
2. **Generate:** Call `generate_spec_doc(spec_path="<path>", validate_only=False)`. This generates the `.docx` and saves `spec.json` and `workspace.zip` alongside it.
