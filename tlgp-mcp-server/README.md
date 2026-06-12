# tlgp-mcp-server

MCP (Model Context Protocol) server that exposes the TLGP annotation and document generation toolchain as discoverable tools for AI agents.

## Overview

This server exposes two tools — one per underlying package — and one orchestration prompt:

| Type | Count | Purpose |
|---|---|---|
| **Tools** | 2 | Launch the annotation GUI, generate .docx specification documents |
| **Prompts** | 1 | Step-by-step workflow guiding the agent through the full pipeline |

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
      "args": ["run", "--directory", "/Volumes/Lexar2TB/Dev/tlgp-tools", "python", "-m", "tlgp_mcp_server"]
    }
  }
}
```

3. Save the file and click **Refresh** in the MCP Servers panel.
4. The server should appear with 2 tools and 1 prompt.

### Android Studio (Gemini)

1. Open **Settings** → **Tools** → **AI** → **MCP Servers**.
2. Check **Enable MCP Servers**.
3. Add the following configuration:

```json
{
  "mcpServers": {
    "tlgp-tools": {
      "command": "uv",
      "args": ["run", "--directory", "/Volumes/Lexar2TB/Dev/tlgp-tools", "python", "-m", "tlgp_mcp_server"]
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
npx -y @modelcontextprotocol/inspector uv run python -m tlgp_mcp_server
```

### Direct CLI

```bash
uv run python -m tlgp_mcp_server
```

## Tools

### `launch_annotator`

Spawns the TLGP Annotation Tool GUI as a background process. The user annotates screenshots with component boxes and exports when finished.

**Args:**
- `output_dir` — directory where the tool saves exported files
- `screenshot_path` — optional screenshot image path to pre-load
- `session_path` — optional previously exported session JSON to re-edit (mutually exclusive with `screenshot_path`)

### `generate_spec_doc`

Validates analysis data and generates a formatted `.docx` specification document. Accepts a complete analysis dict (conforming to the AnalysisData schema), validates it against the Pydantic schema, cross-checks that all referenced images exist, and generates the document.

**Args:**
- `analysis` — complete analysis data dict (see the `spec_doc_workflow` prompt for the full schema reference)
- `output_path` — optional path for the generated `.docx` (defaults to `<screen_name>.docx` in `exportDir`)
- `validate_only` — if `True`, validate without generating (useful for catching errors early)

## Prompts

### `spec_doc_workflow`

Complete workflow for creating a screen specification document. Guides the agent through: launching the annotator → reading annotation exports → vision analysis → codebase analysis → validation → generation. Includes the full analysis schema reference, control type classification guide, annotation export format documentation, and a concrete example inline.

**Args:**
- `section_prefix` (default: `"1.1"`) — section number prefix for headings

## Architecture

```
Agent ──MCP──▸ tlgp-mcp-server
                     │
                     ├── launch_annotator ──subprocess──▸ tlgp-annotation-tool (GUI)
                     │
                     └── generate_spec_doc ──import──▸ tlgp-doc-generator
```

- The MCP server imports `tlgp-doc-generator` directly for validation and document generation.
- The annotation tool runs as a detached subprocess (GUI cannot run inside an MCP tool call).
- All document formatting is driven by `spec_format.toml` in the doc-generator package.
