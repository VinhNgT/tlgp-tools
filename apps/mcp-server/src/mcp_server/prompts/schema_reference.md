## analysis.json Schema Reference

Every field maps to a specific location in the generated .docx document.

### Root Fields

| Field | Type | Description |
|---|---|---|
| `sectionPrefix` | `str` | Section number prefix for component headings (e.g., "1.1") |
| `imageDir` | `str` | Path (absolute or relative) to the directory containing cropped images |
| `components` | `list[Component]` | All annotated components. Must be sorted in post-order DFS sequence (child components first, parent components later) |
| `screen` | `Screen` | Screen-level metadata |
| `discrepancies` | `list[Discrepancy]` | Conflicts between screenshots and code |

### Component Fields

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Sequential annotation box ID |
| `label` | `str` | Descriptive Vietnamese component name |
| `description` | `str` | Vietnamese description of the component's purpose |
| `isLeaf` | `bool` | True if component has no children |
| `imageFile` | `str?` | Filename of the component annotated image (e.g. `<uuid>.png`) |
| `children` | `list[ChildElement]` | UI elements inside this component |
| `interactions` | `list[Interaction]` | User action / system reaction pairs |
| `apis` | `list[Api]` | API documentation used by this component (only for non-leaf components) |

### ChildElement Fields

| Field | Type | Description |
|---|---|---|
| `stt` | `int` | Sequential number |
| `label` | `str` | Descriptive Vietnamese element name |
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
| `apis` | `list[Api]` | API documentation used directly by this screen overview |

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

### SubDto Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Name of the nested DTO class |
| `fieldRef` | `str` | Name of the parent field that references this DTO |
| `fields` | `list[ApiParam]` | Fields of the nested DTO (same structure as ApiParam) |

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
