"""Entry point for running the MCP server: python -m mcp_server"""

import os

from tlgp_logger import setup_logging

from mcp_server.server import mcp


def main():
    """Run the TLGP MCP server with stdio transport."""
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    mcp.run()


if __name__ == "__main__":
    main()
