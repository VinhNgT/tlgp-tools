# mcp-server

MCP (Model Context Protocol) server that exposes the TLGP annotation and document generation toolchain as discoverable tools for AI agents.

## Overview

This server exposes five tools and zero prompts:

| Type | Count | Purpose |
|---|---|---|
| **Tools** | 5 | Launch the annotator GUI, manage workspaces, export component crops, and generate spec documents |

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
4. The server should appear with 5 tools.

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

### `generate_spec_doc`

Validates analysis data from a JSON file, generates a formatted `.docx` specification document, and saves the final analysis JSON data alongside it as `analysis.json` for record-keeping. It validates the data against the Pydantic schema, cross-checks that all referenced images exist, and generates the document.

**Args:**
- `analysis_path` — path to the `analysis.json` file on disk.
- `output_path` — optional path for the generated `.docx` (defaults to `<screen_name>.docx` in `imageDir`). The analysis JSON data will also be saved next to it.
- `validate_only` — if `True`, validate without generating (useful for catching errors early)

## Architecture

```
Agent ──MCP──▸ mcp-server
                     │
                     ├── launch_annotator ──subprocess──▸ tlgp-annotation-tool (GUI)
                     │
                     └── generate_spec_doc ──import──▸ doc-generator
```

- The MCP server imports `doc-generator` directly for validation and document generation.
- The annotation tool runs as a detached subprocess (GUI cannot run inside an MCP tool call).
- All document formatting is driven by `spec_format.toml` in the doc-generator package.
