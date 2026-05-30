from .composition import build_mcp_server_from_env


def main() -> None:
    """Run the Lunaris MCP capability registry over stdio (the `lunaris-mcp` entry point)."""
    build_mcp_server_from_env().run(transport="stdio")


if __name__ == "__main__":
    main()
