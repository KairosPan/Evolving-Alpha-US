"""Run the alpaca-kit MCP server on stdio: python -m alpaca_kit.mcp

The toolset is built from the ambient environment at boot - APCA keys, ALPHA_PIT_ROOT and the
operator-only ALPACA_KIT_ENABLE_ORDERS decide which tools exist. The dsh profile mounts exactly
this command.
"""
from alpaca_kit.mcp.server import build_server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
