"""Network Integration country reference read tool."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_countries_tools(mcp: FastMCP) -> None:
    """Register the global country reference tool."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_countries(
        ctx: Context,
        offset: int = 0,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=200,
                description="Page size (default 200). Maximum 200 or unifi_max_list_items, whichever is lower.",
            ),
        ] = 200,
    ) -> dict[str, Any]:
        """List ISO country codes and names (Network Integration API).

        This is a global reference catalog; it does not select or change a
        site's regulatory domain. No resolved site UUID is required.

        Args:
            ctx: FastMCP request context.
            offset: Page offset (default 0). Bounded by ``unifi_max_list_offset``.
            limit: Page size (default 200). Maximum 200 or
                ``unifi_max_list_items``, whichever is lower.

        Returns:
            The paginated ``{data, offset, limit, count, totalCount}`` envelope
            containing country ``code`` and ``name`` fields, with sensitive
            fields redacted.

        Raises:
            ToolError: If pagination exceeds configured or endpoint bounds, or the API
                rejects or cannot complete the request.
        """
        context = get_server_context(ctx)
        bound_pagination(context.config, offset=offset, limit=limit)
        if limit > 200:
            raise UniFiBadRequestError(f"limit must be between 1 and 200 (got {limit!r})")
        return redact_secrets(await context.clients["network_integration"].list_countries(offset=offset, limit=limit))
