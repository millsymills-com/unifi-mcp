"""Pin parameter guidance in tools/list for the three enum-bearing tools."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from unifi_mcp.tools.protect.cameras import register_camera_tools
from unifi_mcp.tools.site_manager.metrics import register_site_manager_metrics_tools


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "unifi_site_manager_get_isp_metrics",
            {
                "metric_type": "Metric aggregation window: 5m or 1h.",
                "begin_timestamp": "ISO-8601 range start; omitted uses the upstream default range.",
                "end_timestamp": "ISO-8601 range end.",
                "duration": "Duration window, e.g. 24h, as an alternative to an explicit begin/end range.",
            },
        ),
        (
            "unifi_site_manager_query_isp_metrics",
            {
                "metric_type": "Metric aggregation window: 5m or 1h.",
                "sites": "Site selectors with hostId, siteId and optional beginTimestamp/endTimestamp ranges.",
            },
        ),
        (
            "unifi_protect_set_recording_mode",
            {
                "camera_id": "The camera ID.",
                "mode": "Recording mode. never disables recording and requires confirm=True.",
                "pre_padding": "Pre-event recording padding in seconds.",
                "post_padding": "Post-event recording padding in seconds.",
                "confirm": ("Must be True for mode=never; ignored for other modes. Disabled footage is unrecoverable."),
            },
        ),
    ],
)
async def test_tools_list_parameter_guidance(name, expected):
    # Register without the production lifespan: tools/list makes no upstream calls.
    server = FastMCP("parameter-guidance-test")
    register_camera_tools(server)
    register_site_manager_metrics_tools(server)
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    tool = tools[name]
    properties = tool.input_schema["properties"]
    assert {key: value.get("description") for key, value in properties.items()} == expected
    assert "ctx" not in properties
    assert "ctx:" not in (tool.description or "")
    if name == "unifi_protect_set_recording_mode":
        assert properties["confirm"]["default"] is False
        assert tool.annotations is not None
        assert tool.annotations.destructive_hint is True
