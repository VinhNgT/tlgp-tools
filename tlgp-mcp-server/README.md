# tlgp-mcp-server

MCP (Model Context Protocol) server that exposes the TLGP annotation and document generation toolchain as discoverable tools for AI agents.

## Overview

This server bridges the gap between the TLGP toolchain and AI coding agents. Instead of copy-pasting an 800-line workflow document, agents can discover and call structured tools via MCP.

### What it provides

| Type | Count | Purpose |
|---|---|---|
| **Tools** | 6 | Executable actions: launch annotator, inspect directories, scaffold/validate/generate |
| **Resources** | 3 | Reference data: analysis.json schema, control type guide, formatting spec |
| **Prompts** | 1 | Step-by-step workflow for creating a specification document |

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
4. The server should appear with 6 tools, 3 resources, and 1 prompt.

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

Spawns the TLGP Annotation Tool GUI as a background process. The user annotates screenshots and exports when finished.

### `list_exports`

Inspects an output directory and reports its state: `empty`, `annotations_only`, `ready`, `complete`, `malformed`, or `not_found`. Guides the agent on what to do next.

### `parse_annotations`

Reads the annotation tool's exported JSON and returns a validated, structured component hierarchy.

### `scaffold_analysis`

Auto-generates an `analysis.json` template from annotation exports. Pre-fills everything derivable (component IDs, labels, image mappings, child numbering). Leaves empty slots for fields requiring agent intelligence: control types, descriptions, interactions, and API data.

### `validate_analysis`

Validates a completed `analysis.json` against the doc generator's Pydantic schema. Cross-checks that all referenced images exist. Reports blocking errors and informational warnings.

### `generate_docx`

Builds a `.docx` specification document from a validated `analysis.json`. All formatting (fonts, colors, table widths) is applied automatically from `spec_format.toml`.

## Resources

| URI | Description |
|---|---|
| `tlgp://schema/analysis-json` | Documented schema for every field in `analysis.json` |
| `tlgp://schema/control-types` | Visual guide for classifying UI controls |
| `tlgp://spec/formatting` | Current formatting configuration (read-only) |

## Prompts

### `create_spec_doc`

Complete workflow for creating a screen specification document. Guides the agent through: inspecting the workspace → launching the annotator → scaffolding → vision analysis → codebase analysis → validation → generation.

**Arguments:**

- `section_prefix` (default: `"1.1"`): Section number prefix for headings.

## Architecture

```
Agent ──MCP──▸ tlgp-mcp-server ──import──▸ tlgp-doc-generator
                    │
                    └──subprocess──▸ tlgp-annotation-tool (GUI)
```

- The MCP server imports `tlgp-doc-generator` directly for validation and generation.
- The annotation tool runs as a detached subprocess (GUI cannot run inside an MCP tool call).
- All formatting is driven by `spec_format.toml` in the doc-generator package.
