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


---

## analysis.json Schema Reference

Every field maps to a specific location in the generated .docx document.

### Root Fields

| Field | Type | Description |
|---|---|---|
| `sectionPrefix` | `str` | Section number prefix for component headings (e.g., "1.1") |
| `exportDir` | `str` | Absolute path to the annotation export directory |
| `components` | `list[Component]` | All annotated components |
| `screen` | `Screen` | Screen-level metadata |
| `apis` | `list[Api]` | API documentation from codebase analysis |
| `discrepancies` | `list[Discrepancy]` | Conflicts between screenshots and code |

### Component Fields

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Sequential annotation box ID |
| `label` | `str` | Component name (from annotation label) |
| `description` | `str` | Vietnamese description of the component's purpose |
| `isLeaf` | `bool` | True if component has no children |
| `imageFile` | `str?` | Filename of the component annotated image (e.g. `<uuid>.png`) |
| `children` | `list[ChildElement]` | UI elements inside this component |
| `interactions` | `list[Interaction]` | User action / system reaction pairs |

### ChildElement Fields

| Field | Type | Description |
|---|---|---|
| `stt` | `int` | Sequential number |
| `label` | `str` | Element name (from annotation label) |
| `controlType` | `str` | UI control type (Button, Text, Icon, etc.) |
| `required` | `str` | Whether the field is required |
| `maxLength` | `str` | Maximum input length |
| `editable` | `str` | Whether the element is editable |
| `description` | `str` | Vietnamese description |

### Interaction Fields

| Field | Type | Description |
|---|---|---|
| `action` | `str` | What the user does |
| `reaction` | `str` | What the system does in response |

### Screen Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Screen name (Vietnamese) |
| `description` | `str` | Screen description (Vietnamese) |
| `imageFiles` | `list[str]` | Root annotated image filenames |
| `topLevelChildren` | `list[ChildElement]` | Top-level component summary |
| `interactions` | `list[Interaction]` | Screen-level interactions |

### Api Fields

| Field | Type | Description |
|---|---|---|
| `number` | `int` | Sequential API number |
| `method` | `str` | HTTP method (GET, POST, PUT, DELETE) |
| `title` | `str` | Vietnamese title of what the API does |
| `url` | `str` | Endpoint URL path |
| `requestParams` | `list[ApiParam]` | Query/path parameters |
| `requestBodyType` | `str` | Name of the DTO class used as request body |
| `requestDescription` | `str` | Additional request notes |
| `responseType` | `str` | Name of the response DTO class |
| `responseFields` | `list[ApiParam]` | Response fields |
| `responseDescription` | `str` | Additional response notes |
| `subDtos` | `list[SubDto]` | Nested DTOs referenced by the API |

### ApiParam Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Parameter name |
| `meaning` | `str` | Vietnamese description |
| `required` | `str` | "Có" or empty |
| `dataType` | `str` | Data type (String, int, etc.) |
| `limit` | `str` | Value constraints |
| `defaultValue` | `str` | Default value |

### Discrepancy Fields (informational only — never rendered in the .docx)

When the screenshot and code conflict, **prioritize the image** as the source
of truth. Resolve conflicts in favor of what the screenshot shows. Log
discrepancies for transparency, but they do not appear in the output document.

| Field | Type | Description |
|---|---|---|
| `location` | `str` | Where the discrepancy was found |
| `imageObservation` | `str` | What the screenshot shows |
| `codeObservation` | `str` | What the code shows |
| `resolution` | `str` | How the discrepancy was resolved (optional) |

---

## UI Control Type Classification Guide

### Control Types

| Type | Visual Indicators | Common Examples |
|---|---|---|
| `Button` | Rounded rectangle with text, solid or outlined fill, tap target | "Mua ngay", "Thêm vào giỏ", back arrow button |
| `Text` | Static label or paragraph, no interactive affordance | Titles, prices, descriptions, timestamps |
| `Icon` | Small graphical symbol, typically ≤32px, no text | Heart, share, arrow, cart, menu dots (⋮) |
| `Image` | Photo area, banner, product image, avatar, logo | Product photos, promotional banners, user avatars |
| `Component` | A nested group containing multiple sub-elements | A card with image+text+button, a header bar |
| `Tabbar` | Horizontal tab-style selector with multiple options | Category tabs, filter tabs |
| `Slide` | Dot indicators or carousel controls | Image carousel dots, page indicators |
| `TextField` | Input field with border/underline, placeholder text | Search bars, form inputs |
| `Checkbox` | Square toggle control, checked/unchecked state | Agreement checkboxes, multi-select options |
| `Switch` | Toggle slider control, on/off state | Settings toggles, feature flags |

### Classification Rules

1. If the element contains multiple distinct sub-elements → `Component`
2. If it's interactive and looks tappable → `Button` (unless it's an icon)
3. If it's a small symbol without text → `Icon`
4. If it's a photo or illustration area → `Image`
5. If it's text content without interactivity → `Text`
6. If it accepts user input → `TextField`
7. When in doubt between Button and Icon: if it has text, it's a Button

### Interaction Inference

| Control Type | Typical Interactions |
|---|---|
| `Button` | Navigate to screen, open bottom sheet, call API, submit form |
| `Icon` | Toggle state (favorite), share content, navigate, open menu |
| `Image` | Open image viewer, navigate to detail screen |
| `Component` | Scroll content, expand/collapse, navigate |
| `TextField` | Show keyboard, filter results, validate input |
| `Tabbar` | Switch displayed content category |
| `Checkbox` / `Switch` | Toggle boolean state, update preferences |

---

## Example: Complete Analysis Dict

```json
{
  "sectionPrefix": "{section_prefix}",
  "exportDir": "./workspace_xyz",
  "components": [
    {
      "id": 1,
      "label": "Header",
      "description": "Thanh tiêu đề phía trên cùng của màn hình",
      "isLeaf": false,
      "imageFile": "a1b2c3d4-e5f6-7890-1234-56789abcdef0.png",
      "children": [
        {
          "stt": 1,
          "label": "Back Button",
          "controlType": "Icon",
          "required": "",
          "maxLength": "",
          "editable": "",
          "description": "Nút quay lại màn hình trước"
        },
        {
          "stt": 2,
          "label": "Title",
          "controlType": "Text",
          "required": "",
          "maxLength": "",
          "editable": "",
          "description": "Tiêu đề màn hình hiển thị tên sản phẩm"
        }
      ],
      "interactions": [
        {
          "action": "Click vào nút Back",
          "reaction": "Hệ thống quay về màn hình trước đó"
        }
      ]
    },
    {
      "id": 2,
      "label": "Banner",
      "description": "",
      "isLeaf": true,
      "imageFile": null,
      "children": [],
      "interactions": []
    }
  ],
  "screen": {
    "name": "Chi tiết sản phẩm",
    "description": "Màn hình hiển thị thông tin chi tiết của sản phẩm",
    "imageFiles": ["raw.png"],
    "topLevelChildren": [
      {
        "stt": 1,
        "label": "Header",
        "controlType": "Component",
        "required": "",
        "maxLength": "",
        "editable": "",
        "description": "Thanh tiêu đề chứa nút quay lại và tên sản phẩm"
      },
      {
        "stt": 2,
        "label": "Banner",
        "controlType": "Image",
        "required": "",
        "maxLength": "",
        "editable": "",
        "description": "Ảnh banner quảng cáo sản phẩm"
      }
    ],
    "interactions": [
      {
        "action": "Mở màn hình",
        "reaction": "Hệ thống gọi API lấy chi tiết sản phẩm và hiển thị"
      }
    ]
  },
  "apis": [
    {
      "number": 1,
      "method": "GET",
      "title": "Lấy chi tiết sản phẩm",
      "url": "/api/v1/products/{id}",
      "requestParams": [
        {
          "name": "id",
          "meaning": "ID sản phẩm",
          "required": "Có",
          "dataType": "int",
          "limit": "",
          "defaultValue": ""
        }
      ],
      "requestBodyType": "",
      "requestDescription": "",
      "responseType": "ProductDetailDto",
      "responseFields": [
        {
          "name": "name",
          "meaning": "Tên sản phẩm",
          "required": "Có",
          "dataType": "String",
          "limit": "",
          "defaultValue": ""
        }
      ],
      "responseDescription": "",
      "subDtos": []
    }
  ],
  "discrepancies": []
}
```
