"""Entry point for running the MCP server: python -m mcp_server"""

from mcp_server.server import mcp


def main():
    """Run the TLGP MCP server with stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
