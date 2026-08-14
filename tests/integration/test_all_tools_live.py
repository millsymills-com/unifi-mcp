"""Live tool-layer audit: invoke every registered tool through the FastMCP client.

Where the existing ``test_network_live.py`` / ``test_protect_live.py`` /
``test_site_manager_live.py`` exercise **client methods**, this module drives
the **MCP tool boundary** that agents actually see. Closes #91.

Marked ``@pytest.mark.integration`` throughout so the default ``not integration``
CI run ignores the file. Run against a configured controller with:

    uv run pytest tests/integration/test_all_tools_live.py -v -m integration

Gating env vars:

* ``UNIFI_NETWORK_API`` (and siblings) — enables the corresponding API's tools.
* ``UNIFI_MODE=readwrite`` — enables the write-CRUD tests. Defaults to readonly.
* ``LIVE_TEST_WRITES=1`` — opt-in for the curated write roundtrips even if the
  server was started in readwrite. Defaults off so accidental runs don't mutate.
* ``LIVE_TEST_DESTRUCTIVE=1`` — opt-in for provision / restart / backup tests.
  These mutate actual devices; they stay disabled by default.

Every tool invocation is captured to ``tests/integration/artifacts/<timestamp>/``
so a diff between runs is easy.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from _pytest.outcomes import OutcomeException
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.integration.conftest import WRITE_GATE_REASON, _normalize_mac, _writes_enabled, live_test_device_macs
from unifi_mcp.server import create_server, server_lifespan

pytestmark = pytest.mark.integration


# ── Helpers & fixtures ─────────────────────────────────────────────────────


def _any_api_configured() -> bool:
    return any(os.environ.get(k) for k in ("UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"))


def _destructive_enabled() -> bool:
    return os.environ.get("LIVE_TEST_DESTRUCTIVE", "").strip() in {"1", "true", "yes"}


@dataclass
class ArtifactWriter:
    root: Path

    def dump(self, tool_name: str, payload: dict[str, Any]) -> None:
        path = self.root / f"{tool_name}.json"
        path.write_text(json.dumps(payload, indent=2, default=str))


@pytest.fixture(scope="session")
def artifacts() -> ArtifactWriter:
    """Create a per-session artifacts dir rooted at tests/integration/artifacts/<ts>."""
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    root = Path(__file__).resolve().parent / "artifacts" / stamp
    root.mkdir(parents=True, exist_ok=True)
    return ArtifactWriter(root=root)


@pytest.fixture
async def live_client():
    """A FastMCP Client connected to a server built from real env config.

    Skips the entire test if no API key is configured.
    """
    if not _any_api_configured():
        pytest.skip("No UNIFI_*_API env vars set; skipping live tool audit")
    server = create_server()
    async with Client(server) as client:
        yield client


# ── Discovery — what tools exist on this server? ──────────────────────────


NO_ARG_READ_TOOLS = {
    # Network stats / system
    "unifi_network_get_health",
    "unifi_network_list_devices",
    "unifi_network_list_devices_basic",
    "unifi_network_list_active_clients",
    "unifi_network_list_configured_clients",
    "unifi_network_list_all_clients",
    "unifi_network_get_sysinfo",
    "unifi_network_list_wlans",
    "unifi_network_list_networks",
    "unifi_network_list_firewall_rules",
    "unifi_network_list_firewall_groups",
    "unifi_network_list_port_forwards",
    "unifi_network_list_routes",
    "unifi_network_list_port_profiles",
    "unifi_network_get_settings",
    # Protect
    "unifi_protect_get_nvr",
    "unifi_protect_list_cameras",
    "unifi_protect_list_chimes",
    "unifi_protect_list_lights",
    "unifi_protect_list_sensors",
    "unifi_protect_list_viewers",
    # Site Manager
    "unifi_site_manager_list_hosts",
    "unifi_site_manager_list_sites",
    "unifi_site_manager_list_devices",
}

# Read tools that exist in the registered set but always 404 against the
# current UniFi APIs. The strict xfail flips to a hard failure if a tool
# starts working again, signaling that its tracking issue can close.
XFAIL_NO_ARG_READ_TOOLS: dict[str, str] = {}

# Read tools that take required args; covered via the detail-fetch harness.
DETAIL_READ_TOOLS = {
    "unifi_network_get_device": ("unifi_network_list_devices", "mac", "mac"),
    "unifi_network_get_client": ("unifi_network_list_active_clients", "mac", "mac"),
    "unifi_network_get_wlan": ("unifi_network_list_wlans", "_id", "wlan_id"),
    "unifi_network_get_network": ("unifi_network_list_networks", "_id", "network_id"),
    "unifi_network_get_firewall_rule": ("unifi_network_list_firewall_rules", "_id", "rule_id"),
    "unifi_network_get_firewall_group": ("unifi_network_list_firewall_groups", "_id", "group_id"),
    "unifi_network_get_port_forward": ("unifi_network_list_port_forwards", "_id", "port_forward_id"),
    "unifi_network_get_route": ("unifi_network_list_routes", "_id", "route_id"),
    "unifi_protect_get_camera": ("unifi_protect_list_cameras", "id", "camera_id"),
}


# ── Read-tool audit ────────────────────────────────────────────────────────


async def _invoke(client: Client, name: str, args: dict[str, Any] | None = None) -> Any:
    """Call a tool and return the structured payload (or raise).

    Prefers ``structured_content`` then ``data`` then the raw result, using
    explicit ``is not None`` checks instead of ``or`` so legitimate empty
    payloads (``{}``, ``[]``) aren't silently degraded to the raw result.
    """
    result = await client.call_tool(name, args or {})
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    data = getattr(result, "data", None)
    if data is not None:
        return data
    return result


class TestReadTools:
    """Audit every read tool surfaced by ``create_server()``. Tools whose
    namespace tag is disabled (e.g. Protect tools when the backend is
    unreachable, after #87) won't appear in ``list_tools()`` and are
    naturally skipped.
    """

    async def test_every_no_arg_read_tool(self, live_client, artifacts):
        tool_defs = {t.name for t in await live_client.list_tools()}
        candidates = sorted(NO_ARG_READ_TOOLS & tool_defs)
        if not candidates:
            pytest.skip("No no-arg read tools registered on this server")

        failures: list[tuple[str, str]] = []
        for tool in candidates:
            try:
                payload = await _invoke(live_client, tool)
                artifacts.dump(tool, {"ok": True, "payload": payload})
            except Exception as exc:
                failures.append((tool, f"{type(exc).__name__}: {exc}"))
                artifacts.dump(tool, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        assert not failures, "Read tools failed:\n" + "\n".join(f"  {n}: {e}" for n, e in failures)

    async def test_detail_read_tools_via_list_first(self, live_client, artifacts):
        tool_defs = {t.name for t in await live_client.list_tools()}
        failures: list[tuple[str, str]] = []
        skipped: list[str] = []

        for detail_tool, (list_tool, id_field, arg_name) in DETAIL_READ_TOOLS.items():
            if detail_tool not in tool_defs or list_tool not in tool_defs:
                continue
            try:
                list_payload = await _invoke(live_client, list_tool)
                items = _unwrap_list(list_payload)
                if not items:
                    skipped.append(f"{detail_tool}: {list_tool} returned no items")
                    continue
                record_id = items[0].get(id_field)
                if record_id is None:
                    skipped.append(f"{detail_tool}: first {list_tool} item missing {id_field}")
                    continue
                detail = await _invoke(live_client, detail_tool, {arg_name: record_id})
                artifacts.dump(detail_tool, {"ok": True, "id": record_id, "payload": detail})
            except Exception as exc:
                failures.append((detail_tool, f"{type(exc).__name__}: {exc}"))
                artifacts.dump(detail_tool, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        assert not failures, "Detail read tools failed:\n" + "\n".join(f"  {n}: {e}" for n, e in failures)

    @pytest.mark.parametrize(
        "tool_name",
        [
            pytest.param(name, marks=pytest.mark.xfail(strict=True, reason=reason))
            for name, reason in XFAIL_NO_ARG_READ_TOOLS.items()
        ],
    )
    async def test_xfail_no_arg_read_tool(self, live_client, artifacts, tool_name):
        """Tools that should fail today per their tracking issue (see the
        ``XFAIL_NO_ARG_READ_TOOLS`` reason strings). Strict xfail flips to a
        hard failure if Ubiquiti restores the endpoint, signaling that the
        tracking issue can close.
        """
        tool_defs = {t.name for t in await live_client.list_tools()}
        if tool_name not in tool_defs:
            pytest.skip(f"{tool_name} not registered (API not configured?)")
        payload = await _invoke(live_client, tool_name)
        # If we got here, the integration API now exposes this endpoint —
        # capture the payload so the operator can confirm the new shape.
        artifacts.dump(tool_name, {"ok": True, "payload": payload})

    async def test_protect_get_snapshot_shape(self, live_client, artifacts):
        """Snapshot tool returns the documented {format, data_base64, size_bytes}
        shape and the decoded bytes are a real JPEG.
        """
        tool_defs = {t.name for t in await live_client.list_tools()}
        if "unifi_protect_get_snapshot" not in tool_defs or "unifi_protect_list_cameras" not in tool_defs:
            pytest.skip("Protect tools not registered")

        cameras = _unwrap_list(await _invoke(live_client, "unifi_protect_list_cameras"))
        if not cameras:
            pytest.skip("No cameras adopted on the NVR")
        camera_id = cameras[0].get("id")
        assert camera_id, f"First camera entry missing id: {cameras[0]!r}"

        payload = await _invoke(live_client, "unifi_protect_get_snapshot", {"camera_id": camera_id})
        artifacts.dump(
            "unifi_protect_get_snapshot",
            {"ok": True, "camera_id": camera_id, "payload": _redact_data_base64(payload)},
        )

        assert isinstance(payload, dict), f"Snapshot payload must be dict, got {type(payload).__name__}"
        assert payload.get("format") == "jpeg", f"Expected format='jpeg', got {payload.get('format')!r}"
        assert payload.get("size_bytes", 0) > 1024, f"Snapshot suspiciously small: {payload.get('size_bytes')} bytes"
        data_b64 = payload.get("data_base64") or ""
        assert data_b64, "Missing or empty data_base64 field"
        decoded = base64.b64decode(data_b64)
        assert decoded.startswith(b"\xff\xd8\xff"), f"Decoded bytes are not a JPEG (first 4 bytes: {decoded[:4]!r})"
        assert len(decoded) == payload["size_bytes"], (
            f"size_bytes={payload['size_bytes']} disagrees with decoded length {len(decoded)}"
        )

    async def test_list_events_tool_boundary(self, live_client, artifacts):
        """``list_events`` through the MCP boundary with an explicit ``limit``.

        The backing ``list/alarm`` path 404s on current UCG firmware (#138);
        the tool stays registered, so the boundary contract is "returns a dict
        envelope, or maps the documented 404 to a ``ToolError``". Either outcome
        validates the argument schema and the error mapping.
        """
        tool_defs = {t.name for t in await live_client.list_tools()}
        if "unifi_network_list_events" not in tool_defs:
            pytest.skip("unifi_network_list_events not registered")
        try:
            payload = await _invoke(live_client, "unifi_network_list_events", {"limit": 5})
        except ToolError as exc:
            artifacts.dump("unifi_network_list_events", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            pytest.skip(f"list_events unavailable on this controller (#138): {exc}")
        artifacts.dump("unifi_network_list_events", {"ok": True, "payload": payload})
        assert isinstance(payload, dict), f"list_events must return dict, got {type(payload).__name__}"
        assert "data" in payload or "meta" in payload, f"Unexpected list_events shape: {sorted(payload)}"

    async def test_get_dpi_stats_tool_boundary(self, live_client, artifacts):
        """``get_dpi_stats`` through the MCP boundary with an explicit ``dpi_type``."""
        tool_defs = {t.name for t in await live_client.list_tools()}
        if "unifi_network_get_dpi_stats" not in tool_defs:
            pytest.skip("unifi_network_get_dpi_stats not registered")
        payload = await _invoke(live_client, "unifi_network_get_dpi_stats", {"dpi_type": "by_app"})
        artifacts.dump("unifi_network_get_dpi_stats", {"ok": True, "payload": payload})
        assert isinstance(payload, dict), f"get_dpi_stats must return dict, got {type(payload).__name__}"
        assert "data" in payload or "meta" in payload, f"Unexpected get_dpi_stats shape: {sorted(payload)}"

    async def test_export_video_tool_boundary(self, live_client, artifacts):
        """``export_video`` through the MCP boundary over a tiny window.

        Mirrors :meth:`test_protect_get_snapshot_shape`. The integration v1
        export endpoint is missing on some firmware (404, #227); a documented
        404 maps to ``ToolError`` and skips. A success must carry the documented
        ``{format: mp4, data_base64, size_bytes}`` shape with self-consistent
        byte length. The window is kept to 1 minute to match the client-level
        test and bound the inline payload.
        """
        tool_defs = {t.name for t in await live_client.list_tools()}
        if "unifi_protect_export_video" not in tool_defs or "unifi_protect_list_cameras" not in tool_defs:
            pytest.skip("Protect tools not registered")
        camera_id = await _first_protect_camera_id(live_client)
        end_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        start_ms = end_ms - 60_000
        try:
            payload = await _invoke(
                live_client,
                "unifi_protect_export_video",
                {"camera_id": camera_id, "start": start_ms, "end": end_ms},
            )
        except ToolError as exc:
            artifacts.dump("unifi_protect_export_video", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            pytest.skip(f"export_video unavailable on this firmware (#227): {exc}")
        artifacts.dump(
            "unifi_protect_export_video",
            {"ok": True, "camera_id": camera_id, "payload": _redact_data_base64(payload)},
        )
        assert isinstance(payload, dict), f"export payload must be dict, got {type(payload).__name__}"
        assert payload.get("format") == "mp4", f"Expected format='mp4', got {payload.get('format')!r}"
        assert payload.get("size_bytes", 0) > 0, f"Empty export: {payload.get('size_bytes')} bytes"
        data_b64 = payload.get("data_base64") or ""
        assert data_b64, "Missing or empty data_base64 field"
        decoded = base64.b64decode(data_b64)
        assert len(decoded) == payload["size_bytes"], (
            f"size_bytes={payload['size_bytes']} disagrees with decoded length {len(decoded)}"
        )


def _redact_data_base64(payload: Any) -> Any:
    """Replace base64 image/video data with a size summary in artifact dumps.

    Snapshot/export payloads carry the entire encoded media inline. Without
    redaction, every artifact run would write multi-megabyte JSON files.
    """
    if isinstance(payload, dict) and "data_base64" in payload:
        return {**payload, "data_base64": f"<{len(payload['data_base64'])} chars redacted>"}
    return payload


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    """Extract the list-of-dicts payload from a tool response.

    Three shapes are observed in this server:
    * Bare ``list[dict]`` — what some Protect tools return raw.
    * ``{"data": [...]}`` — what most Network tools return.
    * ``{"result": [...]}`` — FastMCP's structured-content wrapping for tools
      whose return type is ``list[dict]`` (Protect's list_cameras / list_chimes /
      etc.). ``_invoke`` returns ``structured_content`` first, so this envelope
      reaches us instead of the bare list.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


async def _first_protect_camera_id(client: Client) -> str:
    """Return the id of the first adopted camera, or pytest.skip if none.

    Used by read-only Protect tests to pick a target. Skips cleanly
    rather than failing when no camera is adopted (e.g., NVR exists but
    operator hasn't added a camera yet).

    Read-only only: write tests must resolve their target through
    :func:`_allowlisted_camera_id` so they never mutate a device the
    operator has not approved (#330, footgun behind #271).
    """
    cameras = _unwrap_list(await _invoke(client, "unifi_protect_list_cameras"))
    if not cameras:
        pytest.skip("No cameras adopted on the NVR")
    camera_id = cameras[0].get("id")
    assert camera_id, f"First camera entry missing id: {cameras[0]!r}"
    return camera_id


async def _allowlisted_camera_id(client: Client) -> str:
    """Return the id of the first adopted camera whose MAC is allowlisted.

    Write tests must target only devices the operator has explicitly
    approved via ``LIVE_TEST_DEVICE_MACS``. Blindly writing to ``cameras[0]``
    is the footgun behind the #271 bench-bricking incident, so this helper
    filters the live camera list to the allowlist and returns the first
    match. It ``pytest.skip``s (never fails) when the allowlist is empty or
    no adopted camera matches, so a contributor without the approved test
    camera present gets a clean skip rather than a write to the wrong device.

    Args:
        client: A connected FastMCP client.

    Returns:
        The ``id`` of the first adopted camera whose MAC is in the allowlist.
    """
    allowlist = live_test_device_macs()
    if not allowlist:
        pytest.skip("LIVE_TEST_DEVICE_MACS is unset; refusing to pick a Protect write target (#271/#330)")
    cameras = _unwrap_list(await _invoke(client, "unifi_protect_list_cameras"))
    if not cameras:
        pytest.skip("No cameras adopted on the NVR")
    for cam in cameras:
        mac = _normalize_mac(str(cam.get("mac", "")))
        if mac and mac in allowlist:
            camera_id = cam.get("id")
            assert camera_id, f"Allowlisted camera entry missing id: {cam!r}"
            return camera_id
    pytest.skip(
        "No adopted camera matches LIVE_TEST_DEVICE_MACS; "
        "skipping Protect write test rather than targeting a non-approved device (#271/#330)"
    )


# ── Write-tool audit (opt-in via LIVE_TEST_WRITES=1) ───────────────────────


# #271 behavioural read-backs widened to 15s polls to reduce controller
# pressure during cumulative live sweeps. Provision timeout raised to 45s
# so 15s polls give >=3 observations within budget (avoids one-shot poll
# at the deadline). Restart budget unchanged from #268 (covers AP fully
# cycling state=1 → 0 → 1 with a margin for slow re-association).
_PROVISION_TIMEOUT_S = 45.0
_PROVISION_POLL_S = 15.0
_RESTART_TIMEOUT_S = 120.0
_RESTART_POLL_S = 15.0
_RESTART_OFFLINE_WINDOW_S = 60.0


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestWriteRoundtrips:
    """Curated create → (update →) delete roundtrips with ``mcp-audit-<uuid>``
    names so residual artifacts are trivially identifiable. Each test skips
    cleanly if the list tool returns no baseline.
    """

    async def test_firewall_group_crud(self, live_client, artifacts):
        """Tool-boundary CRUD for firewall groups, including update."""
        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-fwg-{suffix}"
        created = await _invoke(
            live_client,
            "unifi_network_create_firewall_group",
            {"name": name, "group_type": "address-group", "group_members": ["192.0.2.1"]},
        )
        artifacts.dump(f"create_firewall_group-{suffix}", {"ok": True, "payload": created})
        items = _unwrap_list(created)
        assert items, f"Expected created firewall group in response: {created}"
        group_id = items[0]["_id"]

        try:
            new_members = ["192.0.2.1", "192.0.2.2"]
            updated = await _invoke(
                live_client,
                "unifi_network_update_firewall_group",
                {"group_id": group_id, "data": {"group_members": new_members}},
            )
            artifacts.dump(f"update_firewall_group-{suffix}", {"ok": True, "payload": updated})

            read_back = await _invoke(live_client, "unifi_network_get_firewall_group", {"group_id": group_id})
            found = next((g for g in _unwrap_list(read_back) if g.get("_id") == group_id), None)
            assert found is not None, f"Updated group {group_id} not found in get_firewall_group"
            assert sorted(found.get("group_members") or []) == sorted(new_members), (
                f"group_members read-back mismatch: set {new_members!r}, got {found.get('group_members')!r}"
            )
        finally:
            deleted = await _invoke(live_client, "unifi_network_delete_firewall_group", {"group_id": group_id})
            artifacts.dump(f"delete_firewall_group-{suffix}", {"ok": True, "payload": deleted})

    async def test_port_forward_crud(self, live_client, artifacts):
        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-pf-{suffix}"
        # Use RFC5737 addresses (TEST-NET-1 / 198.51.100.0/24) so no live traffic is affected.
        created = await _invoke(
            live_client,
            "unifi_network_create_port_forward",
            {
                "name": name,
                "dst_port": "65001",
                "fwd": "198.51.100.1",
                "fwd_port": "65001",
                "proto": "tcp",
                "enabled": False,
            },
        )
        artifacts.dump(f"create_port_forward-{suffix}", {"ok": True, "payload": created})
        items = _unwrap_list(created)
        assert items, f"Expected created port forward in response: {created}"
        pf_id = items[0]["_id"]

        try:
            new_name = f"{name}-updated"
            updated = await _invoke(
                live_client,
                "unifi_network_update_port_forward",
                {"port_forward_id": pf_id, "data": {"name": new_name}},
            )
            artifacts.dump(f"update_port_forward-{suffix}", {"ok": True, "payload": updated})

            read_back = await _invoke(live_client, "unifi_network_get_port_forward", {"port_forward_id": pf_id})
            found = next((p for p in _unwrap_list(read_back) if p.get("_id") == pf_id), None)
            assert found is not None, f"Updated port-forward {pf_id} not found"
            assert found.get("name") == new_name, (
                f"Read-back name mismatch: set {new_name!r}, got {found.get('name')!r}"
            )
        finally:
            deleted = await _invoke(live_client, "unifi_network_delete_port_forward", {"port_forward_id": pf_id})
            artifacts.dump(f"delete_port_forward-{suffix}", {"ok": True, "payload": deleted})

    async def test_route_crud(self, live_client, artifacts):
        """Tool-boundary CRUD for static routes. #257 was a tool-layer payload
        bug (friendly args → controller `static-route_*` shape) that the
        client-layer route test missed because it bypassed the wrapper. This
        test calls the MCP tool directly so future shape drift fails here.

        TEST-NET-2 (198.51.100.0/24) is reserved for documentation per RFC5737
        and never appears in routable traffic; the route is created disabled
        regardless.
        """
        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-route-{suffix}"
        created = await _invoke(
            live_client,
            "unifi_network_create_route",
            {
                "name": name,
                "network": "198.51.100.0/24",
                "route_type": "nexthop-route",
                "gateway_ip": "192.168.1.1",
                "enabled": False,
            },
        )
        artifacts.dump(f"create_route-{suffix}", {"ok": True, "payload": created})
        items = _unwrap_list(created)
        assert items, f"Expected created route in response: {created}"
        route_id = items[0]["_id"]

        try:
            new_name = f"{name}-updated"
            updated = await _invoke(
                live_client,
                "unifi_network_update_route",
                {"route_id": route_id, "data": {"name": new_name}},
            )
            artifacts.dump(f"update_route-{suffix}", {"ok": True, "payload": updated})

            read_back = await _invoke(live_client, "unifi_network_get_route", {"route_id": route_id})
            found = next(
                (r for r in _unwrap_list(read_back) if r.get("_id") == route_id),
                None,
            )
            assert found is not None, f"Updated route {route_id} not found in get_route response"
            assert found.get("name") == new_name, (
                f"Read-back name mismatch: set {new_name!r}, got {found.get('name')!r}"
            )
        finally:
            deleted = await _invoke(live_client, "unifi_network_delete_route", {"route_id": route_id})
            artifacts.dump(f"delete_route-{suffix}", {"ok": True, "payload": deleted})

    async def test_wlan_update_roundtrip_via_mills_work(self, live_client, artifacts):
        """Tool-boundary ``update_wlan`` round-trip against ``mills_work``.

        Captures the current name via the tool boundary (name is not a
        secret, so the tool's redaction layer doesn't mask it), updates it
        to ``mills_work [mcp-test]``, reads back, then restores the original
        name in ``finally``. Non-destructive — the WLAN stays present and
        clients (if any) keep their association across a name change.

        ``create_wlan`` and ``delete_wlan`` are NOT exercised here: the
        tool-layer ``create_wlan`` only forwards 5 fields (name/security/
        wpa_mode/x_passphrase/enabled) and the controller rejects with
        ``api.err.ApGroupMissing`` because ``ap_group_ids`` /
        ``networkconf_id`` / ``usergroup_id`` aren't passed. See the strict
        xfail below.
        """
        list_resp = await _invoke(live_client, "unifi_network_list_wlans")
        wlans = _unwrap_list(list_resp)
        mills_work = next((w for w in wlans if w.get("name") == "mills_work"), None)
        if mills_work is None:
            pytest.skip("mills_work WLAN not present; cannot run update_wlan roundtrip")
        wlan_id = mills_work["_id"]
        original_name = mills_work["name"]
        artifacts.dump("wlan_update_target", {"wlan_id": wlan_id, "original_name": original_name})

        target_name = f"{original_name} [mcp-test]"
        try:
            updated = await _invoke(
                live_client,
                "unifi_network_update_wlan",
                {"wlan_id": wlan_id, "data": {"name": target_name}},
            )
            artifacts.dump(
                "wlan_update_applied",
                {"wlan_id": wlan_id, "target_name": target_name, "payload": updated},
            )

            read_back = await _invoke(live_client, "unifi_network_get_wlan", {"wlan_id": wlan_id})
            items_rb = _unwrap_list(read_back) or ([read_back] if isinstance(read_back, dict) else [])
            wlan_doc = next((w for w in items_rb if w.get("_id") == wlan_id), None)
            assert wlan_doc is not None, f"WLAN {wlan_id} not found in get_wlan response: {read_back}"
            assert wlan_doc.get("name") == target_name, (
                f"Read-back name mismatch: set {target_name!r}, got {wlan_doc.get('name')!r}"
            )
        finally:
            await _invoke(
                live_client,
                "unifi_network_update_wlan",
                {"wlan_id": wlan_id, "data": {"name": original_name}},
            )
            artifacts.dump("wlan_update_restored", {"wlan_id": wlan_id, "restored_name": original_name})

    async def test_create_wlan_pins_apgroup_missing(self, live_client, artifacts):
        """Pin for the create_wlan tool-layer payload bug.

        The tool only forwards ``name/security/wpa_mode/x_passphrase/enabled``
        — the controller demands ``ap_group_ids`` / ``networkconf_id`` /
        ``usergroup_id`` and rejects with ``api.err.ApGroupMissing``. Same
        class as #257.

        ``pytest.raises(match=...)`` makes the failure mode unambiguous:
        today's bug → ToolError matching ``ApGroupMissing`` → test PASSES;
        after the fix → no exception → ``pytest.raises`` reports DID NOT
        RAISE → test FAILS red, prompting promotion to a real CRUD test.
        Unlike a class-wide ``xfail`` marker, this can't be satisfied by an
        unrelated prelude failure.

        Pre-checks the bench is under the 4-WLAN cap so a cap-error doesn't
        masquerade as the missing-field error.
        """
        wlans = _unwrap_list(await _invoke(live_client, "unifi_network_list_wlans"))
        enabled_count = sum(1 for w in wlans if w.get("enabled"))
        if enabled_count >= 4:
            pytest.skip(f"Bench at WLAN cap ({enabled_count} enabled); cap error would mask the bug")

        with pytest.raises(ToolError, match="ApGroupMissing"):
            await _invoke(
                live_client,
                "unifi_network_create_wlan",
                {
                    "name": f"mcp-audit-wlan-{uuid.uuid4().hex[:8]}",
                    "security": "wpapsk",
                    "wpa_mode": "wpa2",
                    "x_passphrase": f"mcp-audit-pass-{uuid.uuid4().hex[:16]}",
                    "enabled": False,
                },
            )
        artifacts.dump("create_wlan_pin", {"ok": True, "enabled_wlan_count": enabled_count})

    async def test_firewall_rule_crud(self, live_client, artifacts):
        """Tool-boundary CRUD for LAN_IN firewall rules.

        Modern controllers reject scalar-only create payloads with
        ``api.err.FirewallRuleFieldsRequired`` (#90), so this test passes the
        full payload via the tool's ``data`` escape hatch — exercising the
        same path agents use for non-trivial rules. ``192.0.2.0/24``
        (RFC5737 TEST-NET-1) keeps the rule inert against real traffic and
        the rule is created disabled.
        """
        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-fwrule-{suffix}"
        payload = {
            "name": name,
            "ruleset": "LAN_IN",
            "rule_index": 20000,
            "action": "drop",
            "protocol": "all",
            "src_address": "192.0.2.0/24",
            "dst_address": "192.0.2.0/24",
            "enabled": False,
            "logging": False,
            "state_new": True,
            "state_established": True,
            "state_invalid": True,
            "state_related": True,
            "icmp_typename": "",
            "ipsec": "",
            "src_firewallgroup_ids": [],
            "dst_firewallgroup_ids": [],
        }
        created = await _invoke(
            live_client,
            "unifi_network_create_firewall_rule",
            {"name": name, "ruleset": "LAN_IN", "data": payload},
        )
        artifacts.dump(f"create_firewall_rule-{suffix}", {"ok": True, "payload": created})
        items = _unwrap_list(created)
        assert items, f"Expected created firewall rule in response: {created}"
        rule_id = items[0]["_id"]

        try:
            updated = await _invoke(
                live_client,
                "unifi_network_update_firewall_rule",
                {"rule_id": rule_id, "data": {"action": "reject"}},
            )
            artifacts.dump(f"update_firewall_rule-{suffix}", {"ok": True, "payload": updated})

            read_back = await _invoke(live_client, "unifi_network_get_firewall_rule", {"rule_id": rule_id})
            found = next((r for r in _unwrap_list(read_back) if r.get("_id") == rule_id), None)
            assert found is not None, f"Updated rule {rule_id} not found in get_firewall_rule response"
            assert found.get("action") == "reject", (
                f"Read-back action mismatch: set 'reject', got {found.get('action')!r}"
            )
        finally:
            deleted = await _invoke(live_client, "unifi_network_delete_firewall_rule", {"rule_id": rule_id})
            artifacts.dump(f"delete_firewall_rule-{suffix}", {"ok": True, "payload": deleted})

    async def test_reset_dpi_smoke(self, live_client, artifacts):
        """Tool-boundary smoke for ``reset_dpi``.

        Clears DPI counters — no recovery needed and no state to capture.
        Counters re-populate as traffic flows. Lives outside
        ``TestDestructive`` because resetting counters is reversible (next
        packet rebuilds them) and the operation is short.

        Behavioural assertion (#268): the controller's `cmd/stat` envelope
        carries `meta.rc` and only sets it to `"ok"` when the reset actually
        ran. A regression where the tool returns 200 with an empty body or
        a non-ok rc would now fail here. Polling `get_health` for a counter
        drop would be racier than this envelope check (background traffic
        bumps counters between calls).
        """
        resp = await _invoke(live_client, "unifi_network_reset_dpi")
        assert isinstance(resp, dict), f"reset_dpi must return dict, got {type(resp).__name__}"
        artifacts.dump("reset_dpi_smoke", {"ok": True, "payload": resp})
        meta = resp.get("meta")
        assert isinstance(meta, dict), f"reset_dpi response missing meta envelope: {resp!r}"
        assert meta.get("rc") == "ok", f"reset_dpi controller envelope not ok: meta={meta!r}"

    async def test_kick_client_iphone(self, live_client, artifacts):
        """Tool-boundary smoke for ``kick_client``.

        Kicks an iPhone client off its AP (per user authorization
        2026-05-20). The client typically reconnects within seconds.
        Asserts the tool returned a dict response only — a behavioural
        read-back via ``list_active_clients`` would race the client's
        auto-reconnect.
        """
        clients_payload = await _invoke(live_client, "unifi_network_list_active_clients")
        clients_list = _unwrap_list(clients_payload)
        target = next(
            (
                c
                for c in clients_list
                if isinstance(c, dict) and c.get("mac") and "iphone" in (c.get("hostname") or "").lower()
            ),
            None,
        )
        if target is None:
            pytest.skip("No iPhone client found in active client list")
        mac = target["mac"]
        artifacts.dump("kick_target", {"mac": mac, "hostname": target.get("hostname")})

        resp = await _invoke(live_client, "unifi_network_kick_client", {"mac": mac})
        assert isinstance(resp, dict), f"kick_client must return dict, got {type(resp).__name__}"
        artifacts.dump("kick_response", {"ok": True, "mac": mac, "payload": resp})

    async def test_block_unblock_client_roundtrip(self, live_client, artifacts):
        """Tool-boundary block → verify → unblock → verify roundtrip.

        Picks the first active client whose hostname contains ``iphone``
        (case-insensitive). Per user authorization 2026-05-20, iPhone clients
        are designated test devices for block/unblock/guest. Assumes the
        target starts unblocked; the test ends in the unblocked state.

        Skips cleanly if no iPhone client is online.
        """
        clients_payload = await _invoke(live_client, "unifi_network_list_active_clients")
        clients_list = _unwrap_list(clients_payload)
        target = next(
            (
                c
                for c in clients_list
                if isinstance(c, dict)
                and c.get("mac")
                and "iphone" in (c.get("hostname") or "").lower()
                and not c.get("blocked")
            ),
            None,
        )
        if target is None:
            pytest.skip("No unblocked iPhone client found in active client list")
        mac = target["mac"]
        artifacts.dump("block_target", {"mac": mac, "hostname": target.get("hostname")})

        block_resp = None
        try:
            block_resp = await _invoke(live_client, "unifi_network_block_client", {"mac": mac})
            artifacts.dump("block_response", {"ok": True, "payload": block_resp})

            after_block = _unwrap_list(await _invoke(live_client, "unifi_network_list_all_clients"))
            entry = next((c for c in after_block if (c.get("mac") or "").lower() == mac.lower()), None)
            assert entry is not None, f"Blocked client {mac} missing from list_all_clients"
            assert entry.get("blocked") is True, f"Block did not stick: blocked={entry.get('blocked')!r}"
        finally:
            if block_resp is not None:
                unblock_resp = await _invoke(live_client, "unifi_network_unblock_client", {"mac": mac})
                artifacts.dump("unblock_response", {"ok": True, "payload": unblock_resp})
                after_unblock = _unwrap_list(await _invoke(live_client, "unifi_network_list_all_clients"))
                entry = next(
                    (c for c in after_unblock if (c.get("mac") or "").lower() == mac.lower()),
                    None,
                )
                assert entry is not None, f"Unblocked client {mac} missing from list_all_clients"
                assert not entry.get("blocked"), f"Unblock did not stick: blocked={entry.get('blocked')!r}"

    async def test_authorize_guest_rejects_non_guest_client(self, live_client, artifacts):
        """Tool-boundary safety pre-check: ``authorize_guest`` /
        ``unauthorize_guest`` MUST reject a MAC that isn't on a guest network.

        The tool's pre-check (``_assert_client_is_guest`` at
        ``clients/network.py:491``) raises a ``UniFiBadRequestError`` →
        ``ToolError`` whose message ends with "is not on a guest network;
        authorize_guest / unauthorize_guest only apply to guest-portal
        clients." Asserts the exact phrase ``not on a guest network`` so a
        controller-side error that merely contains the words "guest" and
        "network" can't satisfy the check after a refactor that drops the
        pre-check.
        """
        clients_list = _unwrap_list(await _invoke(live_client, "unifi_network_list_active_clients"))
        target = next(
            (
                c
                for c in clients_list
                if isinstance(c, dict)
                and c.get("mac")
                and "iphone" in (c.get("hostname") or "").lower()
                and not c.get("is_guest")
            ),
            None,
        )
        if target is None:
            pytest.skip("No non-guest iPhone client available for the rejection-path test")
        mac = target["mac"]
        artifacts.dump("guest_reject_target", {"mac": mac, "hostname": target.get("hostname")})

        expected_phrase = "not on a guest network"
        with pytest.raises(ToolError, match=expected_phrase) as exc_info:
            await _invoke(live_client, "unifi_network_authorize_guest", {"mac": mac, "minutes": 1})
        artifacts.dump("authorize_guest_reject", {"mac": mac, "error": str(exc_info.value)})

        with pytest.raises(ToolError, match=expected_phrase) as exc_info:
            await _invoke(live_client, "unifi_network_unauthorize_guest", {"mac": mac})
        artifacts.dump("unauthorize_guest_reject", {"mac": mac, "error": str(exc_info.value)})

    async def test_authorize_unauthorize_guest_positive_roundtrip(self, live_client, artifacts):
        """Tool-boundary positive-path roundtrip for ``authorize_guest`` /
        ``unauthorize_guest``.

        Requires a client where ``list_all_clients`` reports ``is_guest:
        True`` — i.e. a device associated with a WLAN configured as a guest
        network. ``_assert_client_is_guest`` (clients/network.py:491) is the
        pre-check that gates this path. Skips cleanly if no such client is
        on the controller, so the test can sit dormant until a guest WLAN
        with a connected client exists.

        Cycle: authorize for 1 minute → verify ``authorized=True`` via
        ``list_all_clients`` → unauthorize → verify ``authorized`` flipped
        off. ``finally`` always issues a final ``unauthorize_guest`` so a
        mid-test failure can't leave a stray authorization.
        """
        clients_payload = await _invoke(live_client, "unifi_network_list_all_clients")
        clients_list = _unwrap_list(clients_payload)
        target = next(
            (c for c in clients_list if isinstance(c, dict) and c.get("mac") and c.get("is_guest") is True),
            None,
        )
        if target is None:
            pytest.skip("No is_guest=True client on the controller; positive guest-auth path unreachable")
        mac = target["mac"]
        original_authorized = bool(target.get("authorized", False))
        artifacts.dump(
            "guest_positive_target",
            {"mac": mac, "hostname": target.get("hostname"), "originally_authorized": original_authorized},
        )

        try:
            auth_resp = await _invoke(live_client, "unifi_network_authorize_guest", {"mac": mac, "minutes": 1})
            assert isinstance(auth_resp, dict), f"authorize_guest must return dict, got {type(auth_resp).__name__}"
            artifacts.dump("guest_positive_authorize", {"ok": True, "payload": auth_resp})

            after_auth = _unwrap_list(await _invoke(live_client, "unifi_network_list_all_clients"))
            entry = next((c for c in after_auth if (c.get("mac") or "").lower() == mac.lower()), None)
            assert entry is not None, f"Authorized client {mac} missing from list_all_clients"
            assert entry.get("authorized") is True, (
                f"authorize_guest did not stick: authorized={entry.get('authorized')!r}"
            )

            unauth_resp = await _invoke(live_client, "unifi_network_unauthorize_guest", {"mac": mac})
            assert isinstance(unauth_resp, dict), (
                f"unauthorize_guest must return dict, got {type(unauth_resp).__name__}"
            )
            artifacts.dump("guest_positive_unauthorize", {"ok": True, "payload": unauth_resp})

            after_unauth = _unwrap_list(await _invoke(live_client, "unifi_network_list_all_clients"))
            entry = next((c for c in after_unauth if (c.get("mac") or "").lower() == mac.lower()), None)
            assert entry is not None, f"Unauthorized client {mac} missing from list_all_clients"
            assert not entry.get("authorized"), (
                f"unauthorize_guest did not stick: authorized={entry.get('authorized')!r}"
            )
        finally:
            if not original_authorized:
                try:
                    await _invoke(live_client, "unifi_network_unauthorize_guest", {"mac": mac})
                except ToolError as exc:
                    artifacts.dump("guest_positive_cleanup_failed", {"error": str(exc)})

    async def test_delete_wlan_via_tool_boundary(self, live_client, artifacts, network_live_client):
        """Tool-boundary positive-path coverage for ``delete_wlan``.

        Self-bootstraps a sacrificial WLAN via the client layer (the
        tool-layer ``create_wlan`` is the bug pinned in
        ``test_create_wlan_pins_apgroup_missing``) then deletes it through
        the MCP tool boundary. Skips when the bench is already at the
        4-WLAN cap or has no template WLAN to copy structural fields from.
        """
        # Self-bootstrap a WLAN via the client layer (the tool's create_wlan
        # is the strict-xfail pinned bug); then delete via the tool boundary
        # to give positive-path coverage that doesn't depend on bench leftovers.
        # Skips cleanly when the bench is already at the 4-WLAN cap.
        wlans = _unwrap_list(await _invoke(live_client, "unifi_network_list_wlans"))
        enabled = sum(1 for w in wlans if w.get("enabled"))
        if enabled >= 4:
            pytest.skip(f"Bench at WLAN cap ({enabled} enabled); cannot create a sacrificial WLAN")
        # Look up structural fields from an existing WLAN so the controller
        # accepts the create (mirrors the create_wlan tool-layer bug workaround).
        template = next((w for w in wlans if w.get("ap_group_ids")), None)
        if template is None:
            pytest.skip("No WLAN with ap_group_ids available as a template for sacrificial create")

        suffix = uuid.uuid4().hex[:8]
        ssid = f"mcp-audit-delwlan-{suffix}"
        passphrase = uuid.uuid4().hex[:16]
        created = await network_live_client.create_wlan(
            {
                "name": ssid,
                "enabled": False,
                "security": "wpapsk",
                "wpa_mode": "wpa2",
                "wpa_enc": "ccmp",
                "x_passphrase": passphrase,
                "is_guest": False,
                "ap_group_ids": template["ap_group_ids"],
                "ap_group_mode": "all",
                "usergroup_id": template["usergroup_id"],
                "networkconf_id": template["networkconf_id"],
                "wlan_band": "both",
                "wlan_bands": ["2g", "5g"],
            }
        )
        created_doc = (created.get("data") or [{}])[0]
        wlan_id = created_doc.get("_id")
        assert isinstance(wlan_id, str), f"Sacrificial create_wlan missing _id: {created}"
        artifacts.dump("delete_wlan_target", {"wlan_id": wlan_id, "name": ssid})

        try:
            deleted = await _invoke(live_client, "unifi_network_delete_wlan", {"wlan_id": wlan_id})
            artifacts.dump(f"delete_wlan-{ssid}", {"ok": True, "payload": deleted})

            after = _unwrap_list(await _invoke(live_client, "unifi_network_list_wlans"))
            still_there = next((w for w in after if w.get("_id") == wlan_id), None)
            assert still_there is None, f"WLAN {wlan_id} ({ssid}) still present after delete_wlan: {still_there}"
        except Exception:
            # Best-effort recovery so a failed assertion doesn't leak the sacrificial WLAN.
            try:
                await network_live_client.delete_wlan(wlan_id)
            except Exception as cleanup_exc:
                artifacts.dump("delete_wlan_cleanup_failed", {"error": str(cleanup_exc)})
            raise

    async def test_update_delete_network_via_tool_boundary(
        self, live_client, artifacts, network_live_client, default_lan_id
    ):
        """Tool-boundary positive path for ``update_network`` and ``delete_network``.

        Self-bootstraps a disposable VLAN via the client layer (the tool-layer
        ``create_network`` is the ``VlanUsed`` bug pinned in
        :meth:`test_create_network_vlan_pins_vlan_enabled`), then updates and
        deletes it through the MCP tool boundary, asserting the read-back and
        confirming removal. Never targets the default LAN; on any failure it
        deletes the VLAN via the client layer so a failed assertion can't leak
        it. Uses VLANs 80-89 (the session sandbox fixture owns 90-99).
        """
        existing = _unwrap_list(await _invoke(live_client, "unifi_network_list_networks"))
        used_vlans = {n.get("vlan") for n in existing if isinstance(n, dict) and n.get("vlan")}
        chosen_vlan = next((v for v in range(80, 90) if v not in used_vlans), None)
        if chosen_vlan is None:
            pytest.skip("VLAN IDs 80-89 are all in use; cannot create a disposable network")

        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-net-{suffix}"
        created = await network_live_client.create_network(
            {
                "name": name,
                "purpose": "corporate",
                "vlan": chosen_vlan,
                "vlan_enabled": True,
                "ip_subnet": f"10.80.{chosen_vlan}.1/24",
                "dhcpd_enabled": False,
            }
        )
        network_id = (created.get("data") or [{}])[0].get("_id")
        assert isinstance(network_id, str), f"Disposable create_network missing _id: {created}"
        assert network_id != default_lan_id, "Refusing to target the default LAN"
        artifacts.dump("update_delete_network_target", {"network_id": network_id, "vlan": chosen_vlan, "name": name})

        try:
            new_name = f"{name}-updated"
            updated = await _invoke(
                live_client,
                "unifi_network_update_network",
                {"network_id": network_id, "data": {"name": new_name}},
            )
            artifacts.dump(f"update_network-{suffix}", {"ok": True, "payload": updated})

            read_back = _unwrap_list(
                await _invoke(live_client, "unifi_network_get_network", {"network_id": network_id})
            )
            found = next((n for n in read_back if n.get("_id") == network_id), None)
            assert found is not None, f"Updated network {network_id} not found via get_network"
            assert found.get("name") == new_name, (
                f"Read-back name mismatch: set {new_name!r}, got {found.get('name')!r}"
            )

            assert network_id != default_lan_id, "Refusing to delete the default LAN"
            deleted = await _invoke(live_client, "unifi_network_delete_network", {"network_id": network_id})
            artifacts.dump(f"delete_network-{suffix}", {"ok": True, "payload": deleted})

            after = _unwrap_list(await _invoke(live_client, "unifi_network_list_networks"))
            still_there = next((n for n in after if n.get("_id") == network_id), None)
            assert still_there is None, f"Network {network_id} still present after delete_network: {still_there}"
        except Exception:
            try:
                await network_live_client.delete_network(network_id)
            except Exception as cleanup_exc:
                artifacts.dump("update_delete_network_cleanup_failed", {"error": str(cleanup_exc)})
            raise

    async def test_create_network_vlan_pins_vlan_enabled(self, live_client, artifacts):
        """Pin for the create_network VLAN payload gap.

        The tool doesn't forward ``vlan_enabled``; controller rejects any
        VLAN-bearing payload with the misleading ``api.err.VlanUsed`` (the
        VLAN isn't in use — the flag is just missing). ``conftest.py``'s
        ``test_vlan_id`` fixture works by going through the client layer
        with the full payload.

        Same inversion-safe ``pytest.raises(match=...)`` pattern as
        ``test_create_wlan_pins_apgroup_missing``: today's bug → ToolError
        matching ``VlanUsed`` → test PASSES; after the fix → no exception →
        DID NOT RAISE → test FAILS red. VLAN range 80-89 (vs the conftest
        fixture's 90-99) avoids fixture collision.
        """
        existing = _unwrap_list(await _invoke(live_client, "unifi_network_list_networks"))
        used_vlans = {n.get("vlan") for n in existing if isinstance(n, dict) and n.get("vlan")}
        chosen_vlan = next((v for v in range(80, 90) if v not in used_vlans), None)
        if chosen_vlan is None:
            pytest.skip("VLAN IDs 80-89 are all in use; cannot attempt sandbox network create")

        with pytest.raises(ToolError, match="VlanUsed"):
            await _invoke(
                live_client,
                "unifi_network_create_network",
                {
                    "name": f"mcp-audit-net-{uuid.uuid4().hex[:8]}",
                    "purpose": "corporate",
                    "subnet": f"10.99.{chosen_vlan}.1/24",
                    "vlan": chosen_vlan,
                    "dhcpd_enabled": False,
                },
            )
        artifacts.dump("create_network_pin", {"ok": True, "vlan": chosen_vlan})

    async def test_port_profile_crud(self, live_client, artifacts, test_vlan_id):
        """Tool-boundary CRUD for switch port profiles.

        Reuses the conftest ``test_vlan_id`` session-scoped sandbox VLAN
        as the profile's ``native_networkconf_id`` (required for
        ``forward=native``). The profile starts with ``poe_mode=off`` and
        flips to ``auto`` during the update step.
        """
        suffix = uuid.uuid4().hex[:8]
        name = f"mcp-audit-pp-{suffix}"
        create_payload = {
            "name": name,
            "forward": "native",
            "native_networkconf_id": test_vlan_id,
            "poe_mode": "off",
        }
        created = await _invoke(
            live_client,
            "unifi_network_create_port_profile",
            {"data": create_payload},
        )
        artifacts.dump(f"create_port_profile-{suffix}", {"ok": True, "payload": created})
        items = _unwrap_list(created)
        assert items, f"Expected created port profile in response: {created}"
        profile_id = items[0]["_id"]

        try:
            updated = await _invoke(
                live_client,
                "unifi_network_update_port_profile",
                {"profile_id": profile_id, "data": {"poe_mode": "auto"}},
            )
            artifacts.dump(f"update_port_profile-{suffix}", {"ok": True, "payload": updated})

            read_back = await _invoke(live_client, "unifi_network_get_port_profile", {"profile_id": profile_id})
            found = next((p for p in _unwrap_list(read_back) if p.get("_id") == profile_id), None)
            assert found is not None, f"Updated port profile {profile_id} not found in get_port_profile"
            assert found.get("poe_mode") == "auto", (
                f"Read-back poe_mode mismatch: set 'auto', got {found.get('poe_mode')!r}"
            )
        finally:
            deleted = await _invoke(live_client, "unifi_network_delete_port_profile", {"profile_id": profile_id})
            artifacts.dump(f"delete_port_profile-{suffix}", {"ok": True, "payload": deleted})

    async def test_provision_device_smoke(self, live_client, artifacts, touched_devices):
        """Tool-boundary smoke for ``provision_device``.

        Force-provisions an online AP that's NOT the primary WAP — pushes
        the current config to it. Skips cleanly if no eligible non-protected
        AP is online. Provisioning is normally non-disruptive (config push,
        not reboot), but is gated by the regular write-test opt-in.

        Behavioural assertion (#268): captures ``provisioned_at`` before the
        call and polls ``list_devices`` for up to ``_PROVISION_TIMEOUT_S`` /
        every ``_PROVISION_POLL_S`` looking for the timestamp to advance.
        Some controllers don't surface ``provisioned_at`` (older firmware /
        different device classes); in that case the test skips after the
        deadline rather than failing — the dict-shape + meta.rc baseline is
        the floor.
        """
        import asyncio as _asyncio

        devices_payload = await _invoke(live_client, "unifi_network_list_devices")
        devices = _unwrap_list(devices_payload)
        protected_raw = os.environ.get("UNIFI_MCP_TEST_PROTECTED_MACS", "")
        protected = {p.strip().lower() for p in protected_raw.split(",") if p.strip()}
        target = next(
            (
                d
                for d in devices
                if isinstance(d, dict)
                and d.get("state") == 1
                and (d.get("mac") or "").lower() not in protected
                and (d.get("type") or "").lower() == "uap"
            ),
            None,
        )
        if target is None:
            pytest.skip("No online non-protected AP available for provision_device smoke")
        mac = target["mac"]
        original_provisioned_at = target.get("provisioned_at")
        artifacts.dump(
            "provision_target",
            {
                "mac": mac,
                "model": target.get("model"),
                "name": target.get("name"),
                "provisioned_at": original_provisioned_at,
            },
        )

        touched_devices.claim(mac, "provision")
        resp = await _invoke(live_client, "unifi_network_provision_device", {"mac": mac})
        assert isinstance(resp, dict), f"provision_device must return dict, got {type(resp).__name__}"
        meta = resp.get("meta") if isinstance(resp, dict) else None
        if isinstance(meta, dict):
            assert meta.get("rc") == "ok", f"provision_device envelope not ok: meta={meta!r}"
        artifacts.dump("provision_response", {"ok": True, "mac": mac, "payload": resp})

        if original_provisioned_at is None:
            pytest.skip(
                f"Device {mac} has no provisioned_at field on this controller; behavioural read-back not observable"
            )

        deadline = _asyncio.get_event_loop().time() + _PROVISION_TIMEOUT_S
        observed_provisioned_at = original_provisioned_at
        while _asyncio.get_event_loop().time() < deadline:
            await _asyncio.sleep(_PROVISION_POLL_S)
            after_devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
            after = next((d for d in after_devices if (d.get("mac") or "").lower() == mac.lower()), None)
            if after is None:
                continue
            observed_provisioned_at = after.get("provisioned_at")
            if observed_provisioned_at and observed_provisioned_at > original_provisioned_at:
                artifacts.dump(
                    "provision_readback",
                    {
                        "ok": True,
                        "mac": mac,
                        "before": original_provisioned_at,
                        "after": observed_provisioned_at,
                    },
                )
                return

        artifacts.dump(
            "provision_readback",
            {
                "ok": False,
                "skipped": True,
                "reason": "provisioned_at did not advance within timeout",
                "mac": mac,
                "before": original_provisioned_at,
                "last_observed": observed_provisioned_at,
            },
        )
        pytest.skip(
            f"provisioned_at on {mac} did not advance within {_PROVISION_TIMEOUT_S}s "
            f"(before={original_provisioned_at}, last={observed_provisioned_at}); "
            "controller may not surface a field bump for this device class"
        )


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestProtectWriteRoundtrips:
    """Curated capture → mutate → read-back → restore roundtrips for the
    Protect camera write tools. Each test runs against the first adopted
    camera and restores the original value in `finally` even on assertion
    failure.
    """

    async def test_recording_mode_roundtrip(self, live_client, artifacts):
        """Capture current recordingSettings.mode (if present), PATCH 'always',
        then restore. The legal modes are always | motion | never | schedule.

        Integration v1 omits ``recordingSettings`` from GET responses on this
        controller, so ``original_mode`` may be None. The restore falls back to
        "always" (safe default) in that case. The test asserts the PATCH call
        succeeds (returns a dict) rather than requiring the written mode to echo
        back via a re-read, because integration v1 GET omits the field.
        """
        camera_id = await _allowlisted_camera_id(live_client)

        before = await _invoke(live_client, "unifi_protect_get_camera", {"camera_id": camera_id})
        original_mode = before.get("recordingSettings", {}).get("mode") if isinstance(before, dict) else None
        artifacts.dump(
            "recording_mode_before",
            {"camera_id": camera_id, "original_mode": original_mode, "snapshot": before},
        )
        # Integration v1 omits recordingSettings from GET; fall back to a safe
        # default so the restore call is always valid.
        original_for_restore = original_mode or "always"
        target = "motion" if original_for_restore != "motion" else "always"

        try:
            applied = await _invoke(
                live_client,
                "unifi_protect_set_recording_mode",
                {"camera_id": camera_id, "mode": target},
            )
            artifacts.dump("recording_mode_applied", {"target": target, "response": applied})
            assert isinstance(applied, dict), f"set_recording_mode must return a dict, got {type(applied).__name__}"
        finally:
            await _invoke(
                live_client,
                "unifi_protect_set_recording_mode",
                {"camera_id": camera_id, "mode": original_for_restore},
            )
            artifacts.dump("recording_mode_restored", {"restored_mode": original_for_restore})

    async def test_smart_detection_roundtrip(self, live_client, artifacts):
        """Capture current smartDetectSettings.objectTypes, set ['person'],
        read back, then restore.
        """
        camera_id = await _allowlisted_camera_id(live_client)

        before = await _invoke(live_client, "unifi_protect_get_camera", {"camera_id": camera_id})
        original = (
            list(before.get("smartDetectSettings", {}).get("objectTypes", [])) if isinstance(before, dict) else None
        )
        artifacts.dump(
            "smart_detection_before",
            {"camera_id": camera_id, "original": original, "snapshot": before},
        )
        if original is None:
            pytest.skip(f"Could not read smartDetectSettings from camera (got {before!r})")

        # AI object detection requires a G4/G5-class camera. The G3 Flex
        # reports featureFlags.smartDetectTypes=[]; setting ['person'] on it
        # would 4xx. Skip until AI-capable hardware is available (#330).
        supported = (before.get("featureFlags") or {}).get("smartDetectTypes") or []
        if "person" not in supported:
            pytest.skip(
                "Camera does not support 'person' smart detection "
                f"(featureFlags.smartDetectTypes={supported!r}); needs an AI-capable G4/G5 (#330)"
            )

        target = ["person"]

        try:
            applied = await _invoke(
                live_client,
                "unifi_protect_set_smart_detection",
                {"camera_id": camera_id, "object_types": target},
            )
            artifacts.dump("smart_detection_applied", {"target": target, "response": applied})

            after = await _invoke(live_client, "unifi_protect_get_camera", {"camera_id": camera_id})
            after_types = (
                list(after.get("smartDetectSettings", {}).get("objectTypes", [])) if isinstance(after, dict) else None
            )
            artifacts.dump("smart_detection_readback", {"after_types": after_types, "snapshot": after})
            assert after_types == target, f"Read-back mismatch: set {target!r}, read back {after_types!r}"
        finally:
            await _invoke(
                live_client,
                "unifi_protect_set_smart_detection",
                {"camera_id": camera_id, "object_types": original},
            )
            artifacts.dump("smart_detection_restored", {"restored": original})

    async def test_update_camera_roundtrip(self, live_client, artifacts):
        """Round-trip a string field (name) and a nested settings field
        (ledSettings.isEnabled) via unifi_protect_update_camera. Exercises both
        the simple-key and nested-dict shapes of PUT cameras/{id} on
        integration v1.
        """
        camera_id = await _allowlisted_camera_id(live_client)

        before = await _invoke(live_client, "unifi_protect_get_camera", {"camera_id": camera_id})
        if not isinstance(before, dict):
            pytest.skip(f"Camera response is not a dict: {before!r}")
        original_name = before.get("name")
        original_led = before.get("ledSettings", {}).get("isEnabled")
        artifacts.dump(
            "update_camera_before",
            {"camera_id": camera_id, "name": original_name, "led": original_led, "snapshot": before},
        )
        if original_name is None or original_led is None:
            pytest.skip(
                f"Camera missing name or ledSettings.isEnabled (got name={original_name!r}, led={original_led!r})"
            )

        target_name = f"{original_name} [mcp-test]"
        target_led = not original_led

        try:
            applied = await _invoke(
                live_client,
                "unifi_protect_update_camera",
                {
                    "camera_id": camera_id,
                    "name": target_name,
                    "led_settings_is_enabled": target_led,
                },
            )
            artifacts.dump(
                "update_camera_applied",
                {"target_name": target_name, "target_led": target_led, "response": applied},
            )

            after = await _invoke(live_client, "unifi_protect_get_camera", {"camera_id": camera_id})
            after_name = after.get("name") if isinstance(after, dict) else None
            after_led = after.get("ledSettings", {}).get("isEnabled") if isinstance(after, dict) else None
            artifacts.dump(
                "update_camera_readback",
                {"after_name": after_name, "after_led": after_led, "snapshot": after},
            )
            assert after_name == target_name, f"name read-back mismatch: set {target_name!r}, read back {after_name!r}"
            assert after_led == target_led, f"led read-back mismatch: set {target_led!r}, read back {after_led!r}"
        finally:
            await _invoke(
                live_client,
                "unifi_protect_update_camera",
                {
                    "camera_id": camera_id,
                    "name": original_name,
                    "led_settings_is_enabled": original_led,
                },
            )
            artifacts.dump(
                "update_camera_restored",
                {"restored_name": original_name, "restored_led": original_led},
            )


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestProtectWriteNegatives:
    """Each Protect write tool with malformed input must surface a ToolError
    (mapped from UniFiError), not a raw httpx exception or a silent success.
    Mutations attempted here are rejected by the controller, so no restoration
    is needed.
    """

    async def test_set_recording_mode_invalid_mode(self, live_client, artifacts):
        camera_id = await _allowlisted_camera_id(live_client)
        with pytest.raises(ToolError) as exc_info:
            await _invoke(
                live_client,
                "unifi_protect_set_recording_mode",
                {"camera_id": camera_id, "mode": "this-is-not-a-real-mode"},
            )
        artifacts.dump(
            "set_recording_mode_invalid",
            {"camera_id": camera_id, "error": str(exc_info.value)},
        )

    async def test_set_smart_detection_bogus_type(self, live_client, artifacts):
        camera_id = await _allowlisted_camera_id(live_client)
        with pytest.raises(ToolError) as exc_info:
            await _invoke(
                live_client,
                "unifi_protect_set_smart_detection",
                {"camera_id": camera_id, "object_types": ["blueGiraffe"]},
            )
        artifacts.dump(
            "set_smart_detection_bogus",
            {"camera_id": camera_id, "error": str(exc_info.value)},
        )


# ── Device LED locate/unlocate cycle (only runs in LIVE_TEST_WRITES mode) ─


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestDeviceLocateCycle:
    async def test_locate_then_unlocate_each_adopted_device(self, live_client, artifacts):
        devices_payload = await _invoke(live_client, "unifi_network_list_devices")
        items = _unwrap_list(devices_payload)
        if not items:
            pytest.skip("No adopted devices to locate")

        online = [d for d in items if isinstance(d, dict) and d.get("state") == 1]
        if not online:
            pytest.skip("No online adopted devices to locate")

        failures: list[tuple[str, str]] = []
        for dev in online:
            mac = dev.get("mac")
            if not mac:
                continue
            try:
                await _invoke(live_client, "unifi_network_locate_device", {"mac": mac})
                await _invoke(live_client, "unifi_network_unlocate_device", {"mac": mac})
                artifacts.dump(f"locate_cycle-{mac}", {"ok": True, "mac": mac})
            except ToolError as exc:
                # Race: device went offline between list_devices and locate. Skip
                # rather than fail the whole cycle. Match the trailing period
                # appended by ``handle_client_error`` so a sibling code such as
                # ``api.err.DeviceOfflineUnknown`` doesn't get silently swallowed.
                if "api.err.DeviceOffline." in str(exc):
                    artifacts.dump(
                        f"locate_cycle-{mac}",
                        {"ok": False, "skipped": True, "reason": "DeviceOffline", "mac": mac},
                    )
                    continue
                failures.append((mac, f"{type(exc).__name__}: {exc}"))
                artifacts.dump(f"locate_cycle-{mac}", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:
                failures.append((mac, f"{type(exc).__name__}: {exc}"))
                artifacts.dump(f"locate_cycle-{mac}", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        assert not failures, "Locate cycle failures:\n" + "\n".join(f"  {m}: {e}" for m, e in failures)


# ── Slow / destructive (opt-in separately via LIVE_TEST_DESTRUCTIVE=1) ────


@pytest.mark.live_write
@pytest.mark.slow
@pytest.mark.write_gated
@pytest.mark.skipif(
    not (_writes_enabled() and _destructive_enabled()),
    reason="Set UNIFI_MODE=readwrite, LIVE_TEST_WRITES=1, and LIVE_TEST_DESTRUCTIVE=1 to run backup + restart tests",
)
class TestDestructive:
    async def test_create_backup(self, live_client, artifacts):
        # Per #89 the backup call may take minutes. The tool bumps the per-request
        # timeout to 300s, so this should complete end-to-end on a live controller.
        payload = await _invoke(live_client, "unifi_network_create_backup")
        artifacts.dump("create_backup", {"ok": True, "payload": payload})

    async def test_run_speedtest_smoke(self, live_client, artifacts):
        """Tool-boundary smoke for ``run_speedtest``.

        Runs a WAN speedtest from the controller — slow (~30-60s), kicks
        off real traffic against speedtest.net. Asserts the tool returns a
        dict; doesn't verify result fields since they're transient and
        controller-version-dependent.
        """
        payload = await _invoke(live_client, "unifi_network_run_speedtest")
        assert isinstance(payload, dict), f"run_speedtest must return dict, got {type(payload).__name__}"
        artifacts.dump("run_speedtest", {"ok": True, "payload": payload})

    async def test_restart_non_protected_ap(self, live_client, artifacts, touched_devices):
        """Tool-boundary smoke for ``restart_device``.

        Picks the first online AP whose MAC is NOT in
        ``UNIFI_MCP_TEST_PROTECTED_MACS`` and whose ``num_sta`` is 0
        (no associated clients), then issues a restart through the tool.
        Skips if no such AP exists.

        Behavioural assertion (#268): polls ``list_devices`` for the device
        to transition ``state=1 → state=0 → state=1`` and for ``last_seen``
        to advance past its pre-call value. The offline transition has an
        inner ``_RESTART_OFFLINE_WINDOW_S`` budget — some restart calls are
        no-ops if the controller decides the device doesn't need a reboot,
        and we skip cleanly rather than fail in that case. The full
        offline→online round trip has the outer ``_RESTART_TIMEOUT_S``
        budget; missing that does fail, since a real restart that never
        comes back is the regression we care about.
        """
        import asyncio as _asyncio

        devices_payload = await _invoke(live_client, "unifi_network_list_devices")
        devices = _unwrap_list(devices_payload)
        protected_raw = os.environ.get("UNIFI_MCP_TEST_PROTECTED_MACS", "")
        protected = {p.strip().lower() for p in protected_raw.split(",") if p.strip()}
        target = next(
            (
                d
                for d in devices
                if isinstance(d, dict)
                and d.get("state") == 1
                and (d.get("type") or "").lower() == "uap"
                and (d.get("mac") or "").lower() not in protected
                and (d.get("num_sta") or 0) == 0
            ),
            None,
        )
        if target is None:
            pytest.skip("No online non-protected AP with zero clients available for restart smoke")
        mac = target["mac"]
        original_last_seen = target.get("last_seen")
        artifacts.dump(
            "restart_target",
            {
                "mac": mac,
                "name": target.get("name"),
                "model": target.get("model"),
                "last_seen": original_last_seen,
            },
        )

        touched_devices.claim(mac, "restart")
        resp = await _invoke(live_client, "unifi_network_restart_device", {"mac": mac})
        assert isinstance(resp, dict), f"restart_device must return dict, got {type(resp).__name__}"
        meta = resp.get("meta") if isinstance(resp, dict) else None
        if isinstance(meta, dict):
            assert meta.get("rc") == "ok", f"restart_device envelope not ok: meta={meta!r}"
        artifacts.dump("restart_response", {"ok": True, "mac": mac, "payload": resp})

        # Phase 1: bounded wait for the device to drop offline. If the AP
        # never goes offline within the inner window, the controller likely
        # treated this as a no-op (firmware version, current state, etc.) —
        # skip rather than fail.
        offline_deadline = _asyncio.get_event_loop().time() + _RESTART_OFFLINE_WINDOW_S
        went_offline = False
        while _asyncio.get_event_loop().time() < offline_deadline:
            await _asyncio.sleep(_RESTART_POLL_S)
            after_devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
            entry = next((d for d in after_devices if (d.get("mac") or "").lower() == mac.lower()), None)
            if entry is not None and entry.get("state") == 0:
                went_offline = True
                break

        if not went_offline:
            artifacts.dump(
                "restart_readback",
                {
                    "ok": False,
                    "skipped": True,
                    "reason": "device never transitioned to state=0",
                    "mac": mac,
                    "offline_window_s": _RESTART_OFFLINE_WINDOW_S,
                },
            )
            pytest.skip(
                f"Device {mac} never went offline within {_RESTART_OFFLINE_WINDOW_S}s; "
                "restart_device may have been a controller-side no-op"
            )

        # Phase 2: bounded wait for the device to come back online with a
        # bumped last_seen. Missing this is a real failure — the restart
        # got far enough to take the AP down but it never re-associated.
        online_deadline = _asyncio.get_event_loop().time() + _RESTART_TIMEOUT_S
        last_observed: dict[str, Any] | None = None
        while _asyncio.get_event_loop().time() < online_deadline:
            await _asyncio.sleep(_RESTART_POLL_S)
            after_devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
            entry = next((d for d in after_devices if (d.get("mac") or "").lower() == mac.lower()), None)
            if entry is None:
                continue
            last_observed = entry
            current_last_seen = entry.get("last_seen")
            if (
                entry.get("state") == 1
                and original_last_seen is not None
                and isinstance(current_last_seen, int)
                and current_last_seen > original_last_seen
            ):
                artifacts.dump(
                    "restart_readback",
                    {
                        "ok": True,
                        "mac": mac,
                        "before_last_seen": original_last_seen,
                        "after_last_seen": current_last_seen,
                    },
                )
                return

        artifacts.dump(
            "restart_readback",
            {
                "ok": False,
                "mac": mac,
                "before_last_seen": original_last_seen,
                "last_observed_state": (last_observed or {}).get("state"),
                "last_observed_last_seen": (last_observed or {}).get("last_seen"),
            },
        )
        raise AssertionError(
            f"Device {mac} went offline but did not return to state=1 with bumped last_seen "
            f"within {_RESTART_TIMEOUT_S}s "
            f"(before_last_seen={original_last_seen}, "
            f"last_observed={last_observed!r})"
        )

    async def test_power_cycle_and_assign_port_profile(
        self, live_client, artifacts, network_live_client, test_vlan_id, protected_macs
    ):
        """Tool-boundary roundtrip for ``power_cycle_port`` + ``assign_port_profile``.

        Requires ``UNIFI_MCP_TEST_TARGET_MAC`` and ``UNIFI_MCP_TEST_PORT_IDX``
        (the conftest-honored env vars). The target should be a switch with
        an empty downstream port — per memory, Lite-16-PoE port 8 is the
        documented safe target.

        Self-contained: creates and deletes its own port profile via the
        client layer so the test doesn't depend on the controller having
        any pre-existing profiles. Captures the device's ``port_overrides``
        snapshot before mutation and restores it in ``finally`` so the
        target port returns to whatever override it had (or didn't have).
        """
        target_mac = os.environ.get("UNIFI_MCP_TEST_TARGET_MAC", "").strip().lower()
        port_idx_raw = os.environ.get("UNIFI_MCP_TEST_PORT_IDX", "").strip()
        if not target_mac or not port_idx_raw:
            pytest.skip("UNIFI_MCP_TEST_TARGET_MAC and UNIFI_MCP_TEST_PORT_IDX must be set")
        assert _normalize_mac(target_mac) not in protected_macs, (
            f"{target_mac} is in protected_macs; refusing to power-cycle"
        )
        try:
            port_idx = int(port_idx_raw)
        except ValueError:
            pytest.skip(f"UNIFI_MCP_TEST_PORT_IDX not an int: {port_idx_raw!r}")

        # Power-cycle first — no test-side capture/restore needed; the controller
        # re-applies PoE state itself once the cycle completes.
        cycle_resp = await _invoke(
            live_client,
            "unifi_network_power_cycle_port",
            {"mac": target_mac, "port_idx": port_idx},
        )
        assert isinstance(cycle_resp, dict), f"power_cycle_port must return dict, got {type(cycle_resp).__name__}"
        artifacts.dump(
            "power_cycle_port",
            {"ok": True, "mac": target_mac, "port_idx": port_idx, "payload": cycle_resp},
        )

        # Capture original port_overrides so the restore in finally is exact.
        devices = await network_live_client.list_devices()
        device = next((d for d in devices.get("data", []) if (d.get("mac") or "").lower() == target_mac), None)
        if device is None:
            pytest.skip(f"Device {target_mac} not found in list_devices")
        device_id = device["_id"]
        original_overrides = list(device.get("port_overrides", []))

        # Throwaway profile via client layer — keeps the test independent of
        # whatever profiles happen to exist on the controller.
        suffix = uuid.uuid4().hex[:8]
        profile_name = f"mcp-audit-pp-assign-{suffix}"
        created_profile = await network_live_client.create_port_profile(
            {
                "name": profile_name,
                "forward": "native",
                "native_networkconf_id": test_vlan_id,
                "poe_mode": "off",
            }
        )
        profile_id = (created_profile.get("data") or [{}])[0].get("_id")
        assert isinstance(profile_id, str), f"Throwaway profile missing _id: {created_profile}"
        artifacts.dump(
            "assign_port_profile_setup",
            {
                "profile_id": profile_id,
                "name": profile_name,
                "original_override_count": len(original_overrides),
            },
        )

        try:
            assign_resp = await _invoke(
                live_client,
                "unifi_network_assign_port_profile",
                {"mac": target_mac, "port_idx": port_idx, "profile_id": profile_id},
            )
            assert isinstance(assign_resp, dict), (
                f"assign_port_profile must return dict, got {type(assign_resp).__name__}"
            )
            artifacts.dump("assign_port_profile", {"ok": True, "payload": assign_resp})
        finally:
            # port_overrides restore failure leaves a live switch port on a
            # sandbox profile — must raise so an operator sees the dirty state.
            try:
                await network_live_client.put(f"rest/device/{device_id}", json={"port_overrides": original_overrides})
                artifacts.dump(
                    "assign_port_profile_restored",
                    {"device_id": device_id, "override_count": len(original_overrides)},
                )
            except Exception as restore_exc:
                artifacts.dump(
                    "assign_port_profile_restore_failed",
                    {"error": str(restore_exc), "device_id": device_id, "port_idx": port_idx},
                )
                raise RuntimeError(
                    f"port_overrides restore failed on device {device_id}; "
                    f"port {port_idx} may still be assigned to sandbox profile {profile_id}. "
                    "Manual cleanup required."
                ) from restore_exc
            # Profile deletion failure is non-load-bearing (orphan profile is
            # harmless clutter); artifact-only is fine.
            try:
                await network_live_client.delete_port_profile(profile_id)
                artifacts.dump("assign_port_profile_temp_deleted", {"profile_id": profile_id})
            except Exception as exc:
                artifacts.dump("assign_port_profile_temp_delete_failed", {"error": str(exc)})


# ── Risky device-lifecycle tools (separately gated) ──────────────────────


def _lifecycle_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _risky_target_mac() -> str:
    """UNIFI_MCP_TEST_RISKY_TARGET_MAC if set, else UNIFI_MCP_TEST_TARGET_MAC."""
    return (
        os.environ.get("UNIFI_MCP_TEST_RISKY_TARGET_MAC", "").strip().lower()
        or os.environ.get("UNIFI_MCP_TEST_TARGET_MAC", "").strip().lower()
    )


_READOPT_TIMEOUT_S = 180.0
_READOPT_POLL_S = 5.0


async def _wait_for_adopted_via_tool(client: Client, mac: str, deadline: float) -> bool:
    """Poll list_devices through the MCP boundary until target reports adopted=True."""
    import asyncio as _asyncio

    while _asyncio.get_event_loop().time() < deadline:
        await _asyncio.sleep(_READOPT_POLL_S)
        devices = _unwrap_list(await _invoke(client, "unifi_network_list_devices"))
        target = next((d for d in devices if (d.get("mac") or "").lower() == mac.lower()), None)
        if target and target.get("adopted"):
            return True
    return False


@pytest.mark.live_write
@pytest.mark.slow
@pytest.mark.write_gated
@pytest.mark.skipif(
    not _writes_enabled(),
    reason=WRITE_GATE_REASON,
)
class TestRiskyDeviceLifecycle:
    """Tool-boundary mirrors of forget/adopt/upgrade.

    Separately gated from ``TestDestructive`` because a botched forget+adopt
    cycle can leave a device unadopted (manual reset required) and
    ``upgrade_device`` initiates a firmware flash. Each test has its own
    env-var gate matching ``test_network_device_lifecycle_live.py`` so an
    operator opts in per-tool.
    """

    @pytest.mark.skipif(
        not _lifecycle_enabled("LIVE_TEST_FORGET_ADOPT"),
        reason="Set LIVE_TEST_FORGET_ADOPT=1 to run the forget→adopt cycle",
    )
    async def test_forget_adopt_cycle(self, live_client, artifacts, touched_devices, protected_macs):
        import asyncio as _asyncio

        mac = _risky_target_mac()
        if not mac:
            pytest.skip("UNIFI_MCP_TEST_RISKY_TARGET_MAC or UNIFI_MCP_TEST_TARGET_MAC must be set")
        assert _normalize_mac(mac) not in protected_macs, f"{mac} is in protected_macs; refusing to cycle"

        devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
        target = next((d for d in devices if (d.get("mac") or "").lower() == mac.lower()), None)
        if target is None:
            pytest.skip(f"Target MAC {mac} not in device list")
        if not target.get("adopted"):
            pytest.skip(f"Target MAC {mac} is not currently adopted; nothing to forget")
        artifacts.dump(
            "forget_adopt_target",
            {"mac": mac, "name": target.get("name"), "model": target.get("model")},
        )

        touched_devices.claim(mac, "forget")
        forget_resp = await _invoke(live_client, "unifi_network_forget_device", {"mac": mac})
        assert isinstance(forget_resp, dict), f"forget_device must return dict, got {type(forget_resp).__name__}"
        artifacts.dump("forget_device", {"ok": True, "payload": forget_resp})

        adopted_again = False
        adopt_claimed = False
        try:
            deadline = _asyncio.get_event_loop().time() + _READOPT_TIMEOUT_S
            while _asyncio.get_event_loop().time() < deadline:
                await _asyncio.sleep(_READOPT_POLL_S)
                devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
                t = next((d for d in devices if (d.get("mac") or "").lower() == mac.lower()), None)
                if t is None:
                    continue
                if t.get("adopted"):
                    adopted_again = True
                    break
                try:
                    if not adopt_claimed:
                        touched_devices.claim(mac, "adopt")
                        adopt_claimed = True
                    adopt_resp = await _invoke(live_client, "unifi_network_adopt_device", {"mac": mac})
                    assert isinstance(adopt_resp, dict), (
                        f"adopt_device must return dict, got {type(adopt_resp).__name__}"
                    )
                    artifacts.dump("adopt_device", {"ok": True, "payload": adopt_resp})
                except ToolError as exc:
                    # Narrowed from bare Exception so schema/AttributeError surface immediately.
                    artifacts.dump("adopt_device_retry", {"error": str(exc)})
                    continue
                adopted_again = await _wait_for_adopted_via_tool(live_client, mac, deadline)
                break
            assert adopted_again, (
                f"forget_adopt cycle: {mac} did not return to adopted state within {_READOPT_TIMEOUT_S}s. "
                "Manual recovery may be required."
            )
        except BaseException as orig_exc:
            # touched_devices.claim raises pytest.fail → _pytest.outcomes.Failed
            # (a BaseException). The guard's whole point is "do NOT touch this
            # MAC again"; running recovery-adopt here would defeat it and
            # re-trigger the cumulative-churn brick scenario (#271). Re-raise
            # OutcomeException unmodified so the guard's signal reaches pytest.
            if isinstance(orig_exc, OutcomeException):
                raise
            # Recovery intentionally bypasses touched_devices guard: this only
            # runs after a genuine controller-side failure left the device
            # unadopted, and a single adopt to restore the bench is strictly
            # less risky than leaving it forgotten. Future edits: do NOT add
            # touched_devices.claim() here — doing so blocks recovery (#271).
            try:
                await _invoke(live_client, "unifi_network_adopt_device", {"mac": mac})
                artifacts.dump("adopt_device_recovery", {"ok": True, "mac": mac})
            except Exception as recovery_exc:
                artifacts.dump("adopt_device_recovery_failed", {"error": str(recovery_exc)})
                raise RuntimeError(
                    f"forget_adopt cycle failed AND recovery adopt_device({mac}) also failed; "
                    f"manual reset required. Original error: {orig_exc!r}"
                ) from recovery_exc
            raise

    @pytest.mark.skipif(
        not _lifecycle_enabled("LIVE_TEST_UPGRADE"),
        reason="Set LIVE_TEST_UPGRADE=1 to run upgrade_device smoke (controller may flash firmware)",
    )
    async def test_upgrade_device_smoke(self, live_client, artifacts, touched_devices, protected_macs):
        """Tool-boundary smoke for ``upgrade_device``.

        Asserts the tool returns a dict whether or not the controller has
        an upgrade to push. On already-current devices the controller may
        either no-op-succeed or surface a ToolError with "already/no
        upgrade/up to date" messaging — both are accepted.
        """
        mac = _risky_target_mac()
        if not mac:
            pytest.skip("UNIFI_MCP_TEST_RISKY_TARGET_MAC or UNIFI_MCP_TEST_TARGET_MAC must be set")
        assert _normalize_mac(mac) not in protected_macs, f"{mac} is in protected_macs; refusing to upgrade"

        devices = _unwrap_list(await _invoke(live_client, "unifi_network_list_devices"))
        target = next((d for d in devices if (d.get("mac") or "").lower() == mac.lower()), None)
        if target is None:
            pytest.skip(f"Target MAC {mac} not in device list")
        artifacts.dump(
            "upgrade_target",
            {
                "mac": mac,
                "name": target.get("name"),
                "model": target.get("model"),
                "version": target.get("version"),
                "upgradable": target.get("upgradable"),
            },
        )

        touched_devices.claim(mac, "upgrade")
        try:
            resp = await _invoke(live_client, "unifi_network_upgrade_device", {"mac": mac})
            assert isinstance(resp, dict), f"upgrade_device must return dict, got {type(resp).__name__}"
            artifacts.dump("upgrade_response", {"ok": True, "mac": mac, "payload": resp})
        except ToolError as exc:
            artifacts.dump("upgrade_response_rejected", {"mac": mac, "error": str(exc)})
            # Tightened phrases so genuine concurrent-upgrade errors
            # ("already in progress") aren't swallowed. Match full phrases
            # the controller emits for already-current devices.
            already_current_phrases = (
                "already running",
                "already on the latest",
                "no upgrade available",
                "no upgrades available",
                "is up to date",
                "not upgradable",
            )
            if not any(phrase in str(exc).lower() for phrase in already_current_phrases):
                raise


# ── Mode-gating sanity: readonly hides writes (no live hardware needed) ────


class TestModeGatingLive:
    async def test_readonly_hides_write_tools(self, live_client):
        """#43 item 3: in readonly mode, write tools must not appear in list_tools()."""
        if os.environ.get("UNIFI_MODE", "readonly").lower() != "readonly":
            pytest.skip("UNIFI_MODE is not readonly; skipping readonly-gate assertion")
        tools = {t.name for t in await live_client.list_tools()}
        # Every write tool's name mirrors its client method; pick a few well-known ones.
        # If readonly gating works, none of these should be visible.
        for destructive in (
            "unifi_network_create_wlan",
            "unifi_network_delete_wlan",
            "unifi_network_restart_device",
            "unifi_network_create_backup",
            "unifi_network_upgrade_device",
            "unifi_protect_update_camera",
        ):
            assert destructive not in tools, f"{destructive} is exposed in readonly mode — readonly gate is broken"


# ── §3d: live per-API degradation matrix ──────────────────────────────────


# Combos enumerated in #97 §3d plus the two completeness combos
# (protect+site_manager, all_three) so a lifespan side-effect that only
# manifests under specific multi-API interactions can't slip past.
# Each entry is (combo_id, frozenset of API env vars that must be set).
_DEGRADATION_MATRIX = [
    ("network_only", frozenset({"UNIFI_NETWORK_API"})),
    ("protect_only", frozenset({"UNIFI_PROTECT_API"})),
    ("site_manager_only", frozenset({"UNIFI_SITE_MANAGER_API"})),
    ("network_and_protect", frozenset({"UNIFI_NETWORK_API", "UNIFI_PROTECT_API"})),
    ("network_and_site_manager", frozenset({"UNIFI_NETWORK_API", "UNIFI_SITE_MANAGER_API"})),
    ("protect_and_site_manager", frozenset({"UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"})),
    ("all_three", frozenset({"UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"})),
    ("none", frozenset()),
]

_API_ENV_TO_CLIENT_KEY = {
    "UNIFI_NETWORK_API": "network",
    "UNIFI_PROTECT_API": "protect",
    "UNIFI_SITE_MANAGER_API": "site_manager",
}

_API_ENV_TO_TOOL_PREFIX = {
    "UNIFI_NETWORK_API": "unifi_network_",
    "UNIFI_PROTECT_API": "unifi_protect_",
    "UNIFI_SITE_MANAGER_API": "unifi_site_manager_",
}

# Per-prefix subset of ``NO_ARG_READ_TOOLS`` (defined above): the minimum
# set of read tools that MUST be registered when the API is enabled.
# A regression that keeps one tool and drops the others would satisfy a
# bare ``any(...)`` presence check, so the assertion below uses this floor.
_NO_ARG_READS_BY_PREFIX = {
    prefix: frozenset(n for n in NO_ARG_READ_TOOLS if n.startswith(prefix))
    for prefix in _API_ENV_TO_TOOL_PREFIX.values()
}

# #240: session-level tracker for the degradation matrix. The matrix's
# per-combo skip on ``validate_connection`` failure makes individual combos
# look healthy when a backend regression nukes every combo containing the
# affected API. The coverage test at the bottom of this class checks that
# every API whose env key is set in the session validated at least once.
_DEGRADATION_SESSION: dict[str, Any] = {
    "validated_at_least_once": set(),
    "combos_with_env_attempted": 0,
}


class TestDegradationMatrixLive:
    """#97 §3d live coverage. For each API-config combination, the
    lifespan walks real backends and ``list_tools()`` reflects exactly
    the validated subset.

    The unit-level mirror in ``tests/unit/test_audit_inventory.py`` covers
    the same logic with stubbed clients; this class adds the missing
    evidence that ``validate_connection`` against real UniFi backends lights
    up exactly the expected tools — no namespace leakage, no orphans.
    """

    @pytest.mark.parametrize(
        ("combo_id", "env_vars"),
        _DEGRADATION_MATRIX,
        ids=[c[0] for c in _DEGRADATION_MATRIX],
    )
    async def test_combo_exposes_only_validated_namespaces(self, combo_id, env_vars, monkeypatch, tmp_path, artifacts):
        # Capture real keys before clearing — monkeypatch.delenv strips them
        # from the process env, so we need their values first.
        preserved = {var: os.environ.get(var) for var in env_vars}
        missing = sorted(v for v, val in preserved.items() if not val)
        if missing:
            pytest.skip(f"{combo_id} requires {missing}; not configured in this env")

        # Build a clean env slice: clear every API key, restore only the
        # ones this combo asks for. Chdir to a tmp dir with no .env so the
        # contributor's repo-root .env can't leak back in.
        for var in _API_ENV_TO_CLIENT_KEY:
            monkeypatch.delenv(var, raising=False)
        for var, val in preserved.items():
            monkeypatch.setenv(var, val)
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        monkeypatch.chdir(tmp_path)

        # Track session-wide coverage so the bottom-of-class test can flag
        # an API that was configured but never validated in any combo
        # (#240). Bumped only for combos with required env vars; the
        # `none` combo doesn't contribute to coverage.
        if env_vars:
            _DEGRADATION_SESSION["combos_with_env_attempted"] += 1

        server = create_server()
        async with server_lifespan(server) as ctx:
            expected_keys = {_API_ENV_TO_CLIENT_KEY[v] for v in env_vars}
            validated_keys = set(ctx.clients.keys())
            _DEGRADATION_SESSION["validated_at_least_once"].update(validated_keys)
            failed_to_validate = expected_keys - validated_keys
            if failed_to_validate:
                pytest.skip(
                    f"{combo_id}: lifespan could not validate {sorted(failed_to_validate)} "
                    "against live backends; check controller reachability"
                )

            tool_names = sorted(t.name for t in await server.list_tools())
            expected_prefixes = {_API_ENV_TO_TOOL_PREFIX[v] for v in env_vars}
            foreign_prefixes = set(_API_ENV_TO_TOOL_PREFIX.values()) - expected_prefixes

            leaks = sorted(n for n in tool_names if any(n.startswith(p) for p in foreign_prefixes))
            assert not leaks, f"{combo_id} leaks foreign-namespace tools: {leaks}"

            for prefix in expected_prefixes:
                namespace_tools = {n for n in tool_names if n.startswith(prefix)}
                expected_subset = _NO_ARG_READS_BY_PREFIX[prefix]
                missing_reads = expected_subset - namespace_tools
                assert not missing_reads, f"{combo_id}: expected reads under {prefix} missing: {sorted(missing_reads)}"
            if not expected_prefixes:
                assert tool_names == [], f"none combo expected zero tools, got: {tool_names}"

            artifacts.dump(
                f"degradation_{combo_id}",
                {
                    "ok": True,
                    "configured": sorted(env_vars),
                    "validated": sorted(validated_keys),
                    "tool_count": len(tool_names),
                },
            )

    def test_each_configured_api_validated_in_some_combo(self):
        """#240: catch the case where every combo containing an API skipped
        on ``validate_connection`` failure. A real client-layer regression
        (broken auth, wrong URL, dropped header) hides behind the per-combo
        "controller unreachable" skip otherwise.
        """
        configured = {_API_ENV_TO_CLIENT_KEY[env] for env in _API_ENV_TO_CLIENT_KEY if os.environ.get(env)}
        if not configured:
            pytest.skip("No UNIFI_*_API env vars set; matrix coverage not applicable")
        if _DEGRADATION_SESSION["combos_with_env_attempted"] == 0:
            pytest.skip("Degradation matrix combos didn't run (deselected?); coverage check N/A")
        missing = configured - _DEGRADATION_SESSION["validated_at_least_once"]
        assert not missing, (
            f"#240: APIs {sorted(missing)} had env keys set but never validated in any combo. "
            "A real validate_connection regression may be hiding behind per-combo skips."
        )


# ── Smoke test that the harness itself doesn't need live hardware ─────────


def test_harness_skips_cleanly_without_env(monkeypatch):
    """Sanity: with all UNIFI_*_API vars unset, the test file loads and the
    read-tool audit skips instead of erroring. Runs in the default CI suite.
    """
    for var in ("UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"):
        monkeypatch.delenv(var, raising=False)
    assert _any_api_configured() is False
