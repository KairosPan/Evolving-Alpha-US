"""alpha.mcp — the kind="mcp" connector channel (Body component C, external tool servers).

A ConnectorEntry with kind="mcp" DECLARES a connection to an operator-registered MCP server by
key (impl_ref -> alpha.mcp.registry.server_names, the data-layer twin of alpha.data.registry): the
declaration carries no command, no credential value, no executable content, so editing an entry can
never grant a capability (data rung R1/R2). The registry ships EMPTY — the mechanism lands dark,
mirroring the operator-registry house pattern; an operator adds a server the way a vendor is added.
"""
