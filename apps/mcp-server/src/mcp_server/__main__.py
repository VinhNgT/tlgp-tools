"""Entry point for running the MCP server: python -m mcp_server"""

import os
import sys

from tlgp_logger import setup_logging

from mcp_server.server import mcp


def main():
    """Run the TLGP MCP server with stdio transport."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(line_buffering=True)

    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    mcp.run()


if __name__ == "__main__":
    main()
