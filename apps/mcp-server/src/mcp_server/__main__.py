"""Entry point for running the MCP server: python -m mcp_server"""

import os
import sys

from tlgp_logger import setup_logging

from mcp_server.server import mcp


def main():
    """Run the TLGP MCP server with stdio transport."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    mcp.run()


if __name__ == "__main__":
    main()
