"""Protect media tools — snapshots and video exports (2 tools)."""

from __future__ import annotations

import base64
from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, tool_handler, validate_id


def register_media_tools(mcp: FastMCP) -> None:
    """Register Protect media tools."""

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_snapshot(ctx: Context, camera_id: str, timestamp: int | None = None) -> dict[str, Any]:
        """Get a JPEG snapshot from a camera.

        The response is base64-encoded inline, so the server caps the snapshot
        at ``UNIFI_MAX_SNAPSHOT_BYTES`` (default 50 MB). Requests above that
        threshold are aborted mid-stream with a UniFiError to avoid OOM.

        Args:
            camera_id: The camera ID.
            timestamp: Unix timestamp in milliseconds for a historical snapshot (optional, omit for live).

        Returns:
            ``{"format": "jpeg", "data_base64": str, "size_bytes": int}``. ``data_base64``
            is the JPEG bytes encoded with standard base64; decode before writing to disk.
        """
        validate_id(camera_id, field="camera_id")
        context = get_server_context(ctx)
        data: bytes = await context.clients["protect"].get_snapshot(
            camera_id, timestamp=timestamp, max_bytes=context.config.unifi_max_snapshot_bytes
        )
        return {
            "format": "jpeg",
            "data_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        }

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_export_video(ctx: Context, camera_id: str, start: int, end: int) -> dict[str, Any]:
        """Export a video clip from a camera for a time range.

        The response is base64-encoded inline, so the server caps the clip at
        ``UNIFI_MAX_EXPORT_BYTES`` (default 500 MB). Requests above that
        threshold are aborted mid-stream with a UniFiError to avoid OOM.

        Args:
            camera_id: The camera ID.
            start: Start timestamp in Unix milliseconds.
            end: End timestamp in Unix milliseconds.

        Returns:
            ``{"format": "mp4", "data_base64": str, "size_bytes": int}``. ``data_base64``
            is the MP4 bytes encoded with standard base64; decode before writing to disk.

        Note:
            The underlying endpoint is missing from Protect integration v1
            on UCK-G2-Plus (Protect 7.0.107). Calls return ``HTTP 404 Entity
            'endpoint' not found``. Tracked in #227; the tool stays
            registered so it works automatically once Ubiquiti exposes the
            endpoint on a future firmware.
        """
        validate_id(camera_id, field="camera_id")
        context = get_server_context(ctx)
        data: bytes = await context.clients["protect"].export_video(
            camera_id, start, end, max_bytes=context.config.unifi_max_export_bytes
        )
        return {
            "format": "mp4",
            "data_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        }
