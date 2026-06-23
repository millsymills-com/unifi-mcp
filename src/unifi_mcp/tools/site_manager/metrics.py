"""Site Manager ISP-metrics tools — read-only performance metrics."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler

# The metric window is interpolated into the request path. ``"5m"`` passes the
# generic ID regex but any other value 404s upstream, so the window is checked
# against this explicit allowlist before any HTTP call rather than via
# ``validate_id``.
_METRIC_TYPES: frozenset[str] = frozenset({"5m", "1h"})


def _validate_metric_type(metric_type: str) -> None:
    if metric_type not in _METRIC_TYPES:
        allowed = ", ".join(sorted(_METRIC_TYPES))
        raise UniFiBadRequestError(f"metric_type: must be one of {{{allowed}}}")


def register_site_manager_metrics_tools(mcp: FastMCP) -> None:
    """Register Site Manager ISP-metrics tools on the given FastMCP server."""

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_get_isp_metrics(
        ctx: Context,
        metric_type: str,
        begin_timestamp: str | None = None,
        end_timestamp: str | None = None,
        duration: str | None = None,
    ) -> dict[str, Any]:
        """Get ISP performance metrics across the account from UniFi Site Manager.

        Secret keys are redacted before the response leaves this tool — see
        ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            metric_type: Metric aggregation window. Must be ``"5m"`` or ``"1h"``.
            begin_timestamp: Optional ISO-8601 start of the time range. When
                omitted, the upstream default range applies.
            end_timestamp: Optional ISO-8601 end of the time range.
            duration: Optional duration window (e.g. ``"24h"``) as an
                alternative to an explicit begin/end range.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``. Each entry
            in ``data`` carries per-site ISP metric periods.

        Raises:
            UniFiBadRequestError: If ``metric_type`` is not ``"5m"`` or ``"1h"``.
        """
        _validate_metric_type(metric_type)
        return redact_secrets(
            await get_server_context(ctx)
            .clients["site_manager"]
            .get_isp_metrics(
                metric_type,
                begin_timestamp=begin_timestamp,
                end_timestamp=end_timestamp,
                duration=duration,
            )
        )

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_query_isp_metrics(
        ctx: Context,
        metric_type: str,
        sites: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Query ISP metrics for specific sites and ranges from UniFi Site Manager.

        This is a read despite using HTTP POST: ``sites`` is a pure selector
        body and mutates nothing upstream. Secret keys are redacted before the
        response leaves this tool — see ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            metric_type: Metric aggregation window. Must be ``"5m"`` or ``"1h"``.
            sites: Site selector list. Each entry identifies a site and its
                optional begin/end time range, e.g.
                ``[{"hostId": "...", "siteId": "...", "beginTimestamp": "...",
                "endTimestamp": "..."}]``.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``.

        Raises:
            UniFiBadRequestError: If ``metric_type`` is not ``"5m"`` or ``"1h"``.
        """
        _validate_metric_type(metric_type)
        return redact_secrets(
            await get_server_context(ctx).clients["site_manager"].query_isp_metrics(metric_type, sites)
        )
