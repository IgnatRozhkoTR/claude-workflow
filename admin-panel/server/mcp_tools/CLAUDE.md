# MCP Tools

MCP tool implementations for the governed workflow. Each module groups related `@mcp.tool()` functions.

All tools share the `mcp` FastMCP instance and `with_mcp_workspace` decorator from `__init__.py`.
Tool modules are auto-imported by `__init__.py` to trigger registration.

To add a new tool: create a function with `@mcp.tool()` in the relevant module, or create a new module and add its import to `__init__.py`.
