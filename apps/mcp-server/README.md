# mcp-server

MCP (Model Context Protocol) server that exposes the TLGP annotation and document generation toolchain as discoverable tools for AI agents.

## Overview

This server exposes four tools and five resources:

| Type | Count | Purpose |
|---|---|---|
| **Tools** | 4 | Launch the annotator GUI, manage workspaces, export component crops, and generate spec documents |
| **Resources** | 5 | Read-only access to workflow guides, schema definitions, classification rules, example analysis, and the active workspace state |

## Installation

```bash
# From the monorepo root
uv sync
```

## Setup

### Antigravity IDE

1. Open the side panel → click **"..."** → **MCP Servers** → **Manage MCP Servers** → **View raw config**.
2. This opens `~/.gemini/config/mcp_config.json`. Add the `tlgp-tools` entry:

```json
{
  "mcpServers": {
    "tlgp-tools": {
      "command": "uv",
      "args": ["run", "--directory", "/Volumes/Lexar2TB/Dev/tlgp-tools", "tlgp-mcp"]
    }
  }
}
```

3. Save the file and click **Refresh** in the MCP Servers panel.
4. The server should appear with 4 tools and 5 resources.

### Android Studio (Gemini)

1. Open **Settings** → **Tools** → **AI** → **MCP Servers**.
2. Check **Enable MCP Servers**.
3. Add the following configuration:

```json
{
  "mcpServers": {
    "tlgp-tools": {
      "command": "uv",
      "args": ["run", "--directory", "/Volumes/Lexar2TB/Dev/tlgp-tools", "tlgp-mcp"]
    }
  }
}
```

4. Use Gemini's **Agent Mode** to access the tools.

> [!NOTE]
> Replace `/Volumes/Lexar2TB/Dev/tlgp-tools` with the actual absolute path to the monorepo on your machine.

### Testing with MCP Inspector

```bash
cd /Volumes/Lexar2TB/Dev/tlgp-tools
npx -y @modelcontextprotocol/inspector uv run tlgp-mcp
```

### Direct CLI

```bash
uv run tlgp-mcp
```

## Tools

### `launch_annotator`

Spawns the TLGP Annotation Tool GUI as a background process. The user annotates screenshots with component boxes and exports when finished.

**Args:**
- `path` — optional path to a raw screenshot image or a previously exported `.zip` workspace to pre-load.

### `export_images`

Export cropped component images (both raw and annotated) from the workspace screenshot to a directory.

**Args:**
- `output_path` — Absolute path to the destination directory.

### `connect_to_annotator`

Connect the MCP server to a running annotator instance at the specified URL.

**Args:**
- `url` — The URL of the running annotator instance (e.g. `http://127.0.0.1:55432`).

### `generate_spec_doc`

Validates analysis data from a JSON file, generates a formatted `.docx` specification document, and saves the final analysis JSON data alongside it as `analysis.json` for record-keeping. It validates the data against the Pydantic schema, cross-checks that all referenced images exist, and generates the document.

**Args:**
- `analysis_path` — path to the `analysis.json` file on disk.
- `output_path` — optional path for the generated `.docx` (defaults to `<screen_name>.docx` in `imageDir`). The analysis JSON data will also be saved next to it.
- `validate_only` — if `True`, validate without generating (useful for catching errors early)

## Resources

The server exposes read-only data and reference guides to assist with generating valid analysis JSON structures.

- **`tlgp://workspace/state`**: The active annotation hierarchy state in a flattened JSON structure.
- **`tlgp://spec/workflow`**: End-to-end workflow guide for creating specification documents.
- **`tlgp://spec/schema`**: JSON Schema reference for the analysis JSON structure.
- **`tlgp://spec/classification-guide`**: UI Control Type Classification Guide detailing what UI elements fall under which categories.
- **`tlgp://spec/example-analysis`**: Complete example analysis JSON structure for reference.

## Architecture

```text
Agent ──MCP──▸ mcp-server
                     │
                     ├── launch_annotator ──subprocess──▸ tlgp-annotation-tool (GUI)
                     │
                     ├── connect_to_annotator ──http──▸ tlgp-annotation-tool (API)
                     │
                     └── generate_spec_doc ──subprocess──▸ doc-generator
```

- The MCP server invokes `doc-generator` as a subprocess via the CLI to validate data and generate documents, communicating via a structured JSON contract over stdout.
- The annotation tool GUI runs as a detached subprocess (since GUI applications cannot block inside an MCP tool call).
- All document formatting is driven by `spec_format.toml` in the doc-generator package.
