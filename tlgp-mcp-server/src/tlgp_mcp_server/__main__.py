"""Entry point for running the MCP server: python -m tlgp_mcp_server"""

from tlgp_mcp_server.server import mcp


def main():
    """Run the TLGP MCP server with stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
