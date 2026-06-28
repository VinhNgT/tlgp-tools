# mcp-server

MCP (Model Context Protocol) server that exposes the TLGP annotation and document generation toolchain as discoverable tools for AI agents.

## Overview

This server exposes tools, resources, and prompt templates for screenshot annotation and .docx specification document generation:

| Type | Count | Purpose |
|---|---|---|
| **Tools** | 6 | Launch/connect to the annotator GUI, scaffold `spec.json`, programmatically edit spec nodes, validate spec files, and compile final documents |
| **Resources** | 5 | Read-only access to step-by-step workflows, 1-to-1 validation guides, writing & classification rules, example spec JSON, and schemas |
| **Prompts** | 1 | Pre-written workflow prompts to initiate spec generation sessions |

## Installation

```bash
# From the monorepo root
uv sync
```

## Setup

### Antigravity IDE

1. Open the side panel → click **"..."** → **MCP Servers** → **View raw config**.
2. This opens `~/.gemini/config/mcp_config.json`. Add the `tlgp-tools` entry:

```json
{
  "mcpServers": {
    "tlgp-tools": {
      "command": "uv",
      "args": ["run", "--directory", "<absolute_path_to_cloned_repo>", "tlgp-mcp"]
    }
  }
}
```

3. Save the file and click **Refresh** in the MCP Servers panel.
4. The server should appear with 6 tools, 5 resources, and 1 prompt.

### Android Studio (Gemini)

1. Open **Settings** → **Tools** → **AI** → **MCP Servers**.
2. Check **Enable MCP Servers**.
3. Add the following configuration:

```json
{
  "mcpServers": {
    "tlgp-tools": {
      "command": "uv",
      "args": ["run", "--directory", "<absolute_path_to_cloned_repo>", "tlgp-mcp"]
    }
  }
}
```

4. Use Gemini's **Agent Mode** to access the tools.

> [!NOTE]
> Replace `<absolute_path_to_cloned_repo>` with the actual absolute path to the monorepo on your machine (e.g. `C:/Users/username/tlgp-tools` or `/Users/username/tlgp-tools`).

### Testing with MCP Inspector

```bash
cd <absolute_path_to_cloned_repo>
npx -y @modelcontextprotocol/inspector uv run tlgp-mcp
```

### Direct CLI

```bash
uv run tlgp-mcp
```

## Tools

### `launch_annotator`
Launch the annotation tool GUI to draw and export component bounding boxes.
- **Args:**
  - `path` *(optional)* — Absolute file path to a raw screenshot image or a previously exported `.zip` workspace to pre-load.

### `connect_to_annotator`
Connect the MCP server to a running annotator GUI instance at a local URL.
- **Args:**
  - `url` — The local URL (e.g. `http://127.0.0.1:8000`).

### `scaffold_spec`
Generates the base structural skeleton file (`spec.json`) and exports the raw and annotated cropped component images.
- **Args:**
  - `output_dir` — Absolute path to the destination directory.

### `update_spec_node`
Programmatically edits any semantic properties of a specific component or screen node in the specification JSON file.
- **Args:**
  - `spec_path` — Absolute path to `spec.json`.
  - `node_id` — Node ID to update.
  - `label`, `description`, `control_type`, `required`, `editable`, `max_length`, `interactions`, `apis` — Properties to update.

### `validate_spec`
Runs schema validations, cycle checks, complexity limits, and placeholder validation.
- **Args:**
  - `spec_path` — Absolute path to `spec.json`.

### `compile_spec`
Compiles the spec JSON into a final Word specification document (.docx) and bundles the companion `workspace.zip`.
- **Args:**
  - `spec_path` — Absolute path to `spec.json`.
  - `output_path` *(optional)* — Target path for the `.docx` document.

## Resources

The server exposes read-only data and reference guides to assist with generating valid spec JSON structures:

- **`tlgp://spec/workflow`**: Step-by-step workflow guide for creating specification documents.
- **`tlgp://spec/validation-guide`**: Programmatic 1-to-1 validation rule mapping.
- **`tlgp://spec/writing-guide`**: Semantic guidelines (Vietnamese rules, no prefixes) and UI control classification guide.
- **`tlgp://spec/example-analysis`**: Complete reference `spec.json` structure for a Product Detail Screen.
- **`tlgp://spec/schema`**: JSON Schema of the specification JSON structure.

## Prompts

- **`generate_spec`**: Guides the agent step-by-step through the specification workflow. Takes an optional `path` to load a file or starts fresh if omitted.

## Workflow

The intended end-to-end workflow for an AI agent:

```text
User: Launches the prompt template `generate_spec` (optionally specifying mockup.png)
  → Agent calls launch_annotator(path="mockup.png")

User annotates components in the GUI...

User: "Done annotating"
  → Agent calls scaffold_spec(output_dir="...")
  → Agent inspects visual crop files and searches codebase widgets
  → Agent calls update_spec_node() iteratively for each node
  → Agent calls validate_spec()
  → Agent corrects validation errors/warnings via update_spec_node()
  → Agent calls compile_spec()
  → Spec document (.docx) and companion workspace.zip are generated
```

## Architecture

```text
Agent ──MCP──▸ mcp-server
                     │
                     ├── launch_annotator ──subprocess──▸ annotator (GUI)
                     │
                     ├── connect_to_annotator ──http──▸ annotator (API)
                     │
                     ├── scaffold_spec ──http──▸ annotator (API)
                     │
                     ├── update_spec_node ──file update──▸ spec.json
                     │
                     ├── validate_spec ──subprocess──▸ doc-generator (CLI)
                     │
                     └── compile_spec ──subprocess──▸ doc-generator (CLI)
```
