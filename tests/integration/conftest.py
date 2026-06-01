"""Shared fixtures for live-hardware integration tests.

All tests in this directory are tagged ``@pytest.mark.integration`` and
excluded from CI. Run them manually against a configured controller:

    uv run pytest tests/integration/ -v -m integration

Fixtures skip gracefully if the matching ``UNIFI_*_API`` env var is not set,
so a contributor with only Network credentials won't be forced to stub out
Protect / Site Manager.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import TYPE_CHECKING

import pytest
from fastmcp.exceptions import ToolError

if TYPE_CHECKING:
    from collections.abc import Callable

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.clients.site_manager import SiteManagerClient

LOG = logging.getLogger(__name__)


def _csv_env(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _normalize_mac(mac: str) -> str:
    """Fold a MAC to its 12 lowercase hex digits, stripping separators.

    Controllers and operators write the same address as ``E438830FD628``,
    ``e4:38:83:0f:d6:28`` or ``e4-38-83-0f-d6-28``; folding all three to
    ``e438830fd628`` lets allowlist membership compare structurally rather
    than on incidental punctuation or case.

    Args:
        mac: A MAC address in any common separator/case form.

    Returns:
        The 12-hex-digit canonical form, or ``""`` if the input does not
        contain exactly 12 hex digits (caller decides how to treat junk).
    """
    digits = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    return digits if len(digits) == 12 else ""


def live_test_device_macs() -> frozenset[str]:
    """Normalized MACs the operator has explicitly approved for live writes.

    Parsed from the comma-separated ``LIVE_TEST_DEVICE_MACS`` env var. Each
    entry is folded via :func:`_normalize_mac`; unparseable entries are
    dropped. Returns an empty set when the var is unset or empty, which the
    allowlist-target helpers treat as "skip, nothing approved".

    Returns:
        Frozenset of 12-hex-digit canonical MACs.
    """
    macs = (_normalize_mac(item) for item in _csv_env("LIVE_TEST_DEVICE_MACS"))
    return frozenset(m for m in macs if m)


def _network_host() -> str:
    return os.environ.get("UNIFI_NETWORK_HOST", "192.168.1.1")


def _network_port() -> int:
    return int(os.environ.get("UNIFI_NETWORK_PORT", "443"))


def _protect_host() -> str:
    return os.environ.get("UNIFI_PROTECT_HOST", _network_host())


def _protect_port() -> int:
    return int(os.environ.get("UNIFI_PROTECT_PORT", "443"))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture
async def network_live_client():
    """Live NetworkClient. Skips if UNIFI_NETWORK_API is unset."""
    api_key = os.environ.get("UNIFI_NETWORK_API")
    if not api_key:
        pytest.skip("UNIFI_NETWORK_API not set; skipping live Network test")
    site = os.environ.get("UNIFI_NETWORK_SITE", "default")
    client = NetworkClient(
        base_url=f"https://{_network_host()}:{_network_port()}",
        api_key=api_key,
        site=site,
        verify_ssl=_bool_env("UNIFI_NETWORK_VERIFY_SSL"),
        timeout=int(os.environ.get("UNIFI_REQUEST_TIMEOUT", "30")),
        max_retries=int(os.environ.get("UNIFI_MAX_RETRIES", "3")),
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
async def protect_live_client():
    """Live ProtectClient. Skips if UNIFI_PROTECT_API is unset."""
    api_key = os.environ.get("UNIFI_PROTECT_API")
    if not api_key:
        pytest.skip("UNIFI_PROTECT_API not set; skipping live Protect test")
    client = ProtectClient(
        base_url=f"https://{_protect_host()}:{_protect_port()}",
        api_key=api_key,
        verify_ssl=_bool_env("UNIFI_PROTECT_VERIFY_SSL"),
        timeout=int(os.environ.get("UNIFI_REQUEST_TIMEOUT", "30")),
        max_retries=int(os.environ.get("UNIFI_MAX_RETRIES", "3")),
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
async def site_manager_live_client():
    """Live SiteManagerClient. Skips if UNIFI_SITE_MANAGER_API is unset."""
    api_key = os.environ.get("UNIFI_SITE_MANAGER_API")
    if not api_key:
        pytest.skip("UNIFI_SITE_MANAGER_API not set; skipping live Site Manager test")
    client = SiteManagerClient(
        api_key=api_key,
        timeout=int(os.environ.get("UNIFI_REQUEST_TIMEOUT", "30")),
        max_retries=int(os.environ.get("UNIFI_MAX_RETRIES", "3")),
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="session")
async def network_live_client_session():
    """Session-scoped Network client for fixtures that outlive a single test
    (test_vlan_id, default_lan_id, etc.). Tests should keep using the
    function-scoped network_live_client; this fixture exists only for
    other session-scoped fixtures."""
    api_key = os.environ.get("UNIFI_NETWORK_API")
    if not api_key:
        pytest.skip("UNIFI_NETWORK_API not set; skipping live Network test")
    site = os.environ.get("UNIFI_NETWORK_SITE", "default")
    client = NetworkClient(
        base_url=f"https://{_network_host()}:{_network_port()}",
        api_key=api_key,
        site=site,
        verify_ssl=_bool_env("UNIFI_NETWORK_VERIFY_SSL"),
        timeout=int(os.environ.get("UNIFI_REQUEST_TIMEOUT", "30")),
        max_retries=int(os.environ.get("UNIFI_MAX_RETRIES", "3")),
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="session")
async def protected_macs(network_live_client_session: NetworkClient) -> frozenset[str]:
    """MACs that must NEVER be modified. Set via UNIFI_MCP_TEST_PROTECTED_MACS.

    Fail-fast (with a printed device list) if unset.
    """
    raw = _csv_env("UNIFI_MCP_TEST_PROTECTED_MACS")
    if not raw:
        devices = await network_live_client_session.list_devices()
        rows = [
            f"  {d.get('mac', '?')}  {d.get('name', '?')}  ({d.get('model', '?')})" for d in devices.get("data", [])
        ]
        msg = (
            "UNIFI_MCP_TEST_PROTECTED_MACS is unset. The integration suite refuses\n"
            "to run write tools without an explicit protected-device allowlist.\n\n"
            "Available devices on this controller:\n"
            + "\n".join(rows)
            + "\n\nSet UNIFI_MCP_TEST_PROTECTED_MACS to the comma-separated MACs of\n"
            "your gateway, uplinked switch, and uplinked AP, then rerun."
        )
        pytest.fail(msg)
    LOG.warning("Protected MACs (will not be touched): %s", ", ".join(raw))
    return frozenset(raw)


@pytest.fixture(scope="session")
def test_target_mac(protected_macs: frozenset[str]) -> str:
    """MAC of the designated downstream device for disruptive device-action tests.

    Skips dependent tests if UNIFI_MCP_TEST_TARGET_MAC unset.
    Asserts target not in protected_macs.
    """
    target = os.environ.get("UNIFI_MCP_TEST_TARGET_MAC", "").strip().lower()
    if not target:
        pytest.skip("UNIFI_MCP_TEST_TARGET_MAC unset; skipping device-action tests")
    if target in protected_macs:
        pytest.fail(f"UNIFI_MCP_TEST_TARGET_MAC={target} overlaps protected_macs. Refusing to run.")
    return target


@pytest.fixture(scope="session")
def test_client_mac() -> str:
    """MAC of the test client for kick/block/unblock flows.

    Skips dependent tests if UNIFI_MCP_TEST_CLIENT_MAC unset.
    """
    mac = os.environ.get("UNIFI_MCP_TEST_CLIENT_MAC", "").strip().lower()
    if not mac:
        pytest.skip("UNIFI_MCP_TEST_CLIENT_MAC unset; skipping client-action tests")
    return mac


@pytest.fixture(scope="session")
async def default_lan_id(network_live_client_session: NetworkClient) -> str:
    """_id of the default corporate network. Networks-domain tests must
    never target this. Fails the suite if no default LAN is found.
    """
    networks = await network_live_client_session.list_networks()
    corporates = [n for n in networks.get("data", []) if n.get("purpose") == "corporate"]
    # Prefer explicit is_default flag; fall back to first no-VLAN corporate (the base LAN).
    candidate = next((n for n in corporates if n.get("is_default") is True), None)
    if candidate is None:
        candidate = next((n for n in corporates if not n.get("vlan")), None)
    if candidate is None:
        pytest.fail("No default corporate network found; refusing to run write tests.")
    lan_id = candidate.get("_id")
    assert isinstance(lan_id, str), "default LAN _id missing or wrong type"
    LOG.warning("Default LAN _id (off-limits to write tests): %s", lan_id)
    return lan_id


@pytest.fixture(scope="session")
def mcptest_prefix() -> str:
    """All test artifacts named {prefix}{domain}-{uuid4-hex[:8]}.
    Default: 'mcptest-'. Override via UNIFI_MCP_TEST_PREFIX.
    Session-scoped because session fixtures depend on it.
    """
    return os.environ.get("UNIFI_MCP_TEST_PREFIX", "mcptest-").strip()


def _canonical_mac(mac: str) -> str:
    """Canonical 12-hex-digit form of a MAC, separators and case stripped.

    Controllers return the same device as ``aa:bb:cc:11:22:33`` or
    ``aa-bb-cc-11-22-33``; folding both to ``aabbcc112233`` keeps the guard
    from treating them as distinct and silently bypassing (#278). Anything
    that is not exactly 12 hex digits after stripping is unparseable and is
    rejected rather than slipping through as a degenerate key.
    """
    digits = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    if len(digits) != 12:
        pytest.fail(f"TouchedDevices.claim: invalid MAC {mac!r}")
    return digits


class TouchedDevices:
    """Session-scoped guard against repeat destructive ops on the same device.

    A single MAC may be targeted by at most one destructive op
    (forget / adopt / upgrade / provision / restart) per pytest session.
    Cumulative churn within a single session has bricked controllers
    (UCG Ultra factory-reset 2026-05-21) — see #271.
    """

    def __init__(self) -> None:
        self._claims: dict[str, str] = {}

    def claim(self, mac: str, op: str) -> None:
        key = _canonical_mac(mac)
        prior = self._claims.get(key)
        if prior is not None:
            pytest.fail(
                f"Device {key} already touched by {prior} earlier in session; "
                f"refuse to {op} again to avoid cumulative controller corruption (#271)"
            )
        self._claims[key] = op


@pytest.fixture(scope="session")
def touched_devices() -> TouchedDevices:
    """Session-scoped TouchedDevices guard. Per-MAC, one destructive op per session (#271)."""
    return TouchedDevices()


@pytest.fixture
async def cleanup_register():
    """Per-test stack-based cleanup. register(callable, *args, **kwargs)
    pushes a deferred call; finally pops in LIFO order, best-effort runs,
    logs WARNING on failure. Never raises (would mask the test's real failure).
    """
    stack: list[tuple[Callable[..., object], tuple[object, ...], dict[str, object]]] = []

    def register(fn: Callable[..., object], *args: object, **kwargs: object) -> None:
        stack.append((fn, args, kwargs))

    try:
        yield register
    finally:
        while stack:
            fn, args, kwargs = stack.pop()
            try:
                result = fn(*args, **kwargs)
                if inspect.iscoroutine(result):
                    await result
            except Exception as exc:
                LOG.warning("cleanup_register: %s(%s) failed: %s", getattr(fn, "__name__", repr(fn)), args, exc)


@pytest.fixture(scope="session")
async def test_vlan_id(
    network_live_client_session,
    mcptest_prefix: str,
):
    """Session-scoped sandbox VLAN for dependent tests (wlan, port-profiles,
    firewall rules, port-forwards). Created in 90-99 range using lowest
    unused ID. Skipped (not failed) if creation fails.
    """
    existing = await network_live_client_session.list_networks()
    used_vlans = {n.get("vlan") for n in existing.get("data", []) if n.get("vlan")}
    chosen = next((v for v in range(90, 100) if v not in used_vlans), None)
    if chosen is None:
        pytest.skip("VLAN IDs 90-99 are all in use; cannot create sandbox VLAN.")

    name = f"{mcptest_prefix}vlan-{chosen}"
    try:
        # vlan_enabled must be True or the controller rejects with VlanUsed
        created = await network_live_client_session.create_network(
            {
                "name": name,
                "purpose": "corporate",
                "vlan": chosen,
                "vlan_enabled": True,
                "subnet": f"10.99.{chosen}.1/24",
                "dhcpd_enabled": False,
            }
        )
    except Exception as exc:
        pytest.skip(f"Failed to create sandbox VLAN: {exc}")

    vlan_doc = (created.get("data") or [{}])[0]
    network_id = vlan_doc.get("_id")
    if not isinstance(network_id, str):
        pytest.skip(f"Sandbox VLAN response missing _id: {created}")

    LOG.warning("Sandbox VLAN created: id=%s vlan=%d name=%s", network_id, chosen, name)
    try:
        yield network_id
    finally:
        try:
            await network_live_client_session.delete_network(network_id)
            LOG.warning("Sandbox VLAN deleted: %s", network_id)
        except Exception as exc:
            LOG.warning("Sandbox VLAN cleanup failed (id=%s): %s", network_id, exc)


def _contains_tool_error(exc: BaseException | None) -> bool:
    """True if ``exc`` is a ToolError or wraps one via cause/context/group."""
    if exc is None:
        return False
    if isinstance(exc, ToolError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_tool_error(e) for e in exc.exceptions)
    return _contains_tool_error(exc.__cause__) or _contains_tool_error(exc.__context__)


# #271: bench-bricking guardrail. The live write sweep churns controller
# state (networks, port profiles, WLANs, device adoption). When one write
# tool raises an unexpected ToolError, the controller is likely already
# in a degraded state (partial-write residue, stuck transactions). Letting
# the rest of the sweep keep churning has, in practice, factory-reset a
# UCG Ultra. Expected errors guarded by pytest.raises(ToolError, match=...)
# are caught inside the test and never reach this hook, so legitimate
# create_wlan / create_network pins stay green.
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    report: pytest.TestReport = yield
    if (
        report.when == "call"
        and report.failed
        and item.get_closest_marker("live_write") is not None
        and call.excinfo is not None
        and _contains_tool_error(call.excinfo.value)
    ):
        LOG.error("live_write abort triggered by %s: %s", item.nodeid, call.excinfo.getrepr())
        # returncode=2 is pytest's "session interrupted", not 1 ("tests failed").
        # The distinction is deliberate: a #271 safety abort is a controlled
        # interruption of the sweep, and keeping it separate from ordinary
        # failures lets CI/log triage tell the two apart at a glance.
        pytest.exit(
            f"aborting live write sweep — {item.nodeid} raised unexpected ToolError, "
            "refusing to continue churning controller state (#271)",
            returncode=2,
        )
    return report


# #277/#290: CI never collects the integration suite (it runs `-m "not integration"`),
# so a write-gated test class that forgets @pytest.mark.live_write would silently
# lose abort-hook protection until the next manual live run re-bricked the bench.
# Write-gated tests carry the explicit @pytest.mark.write_gated marker (#290); the
# guard keys on that structural signal rather than scraping skipif reason text,
# which was a brittle convention that any reworded reason could silently defeat.
def _is_write_gated(item: pytest.Item) -> bool:
    return item.get_closest_marker("write_gated") is not None


# `items` is filled by name from pytest's (session, config, items) hookspec; the
# leading args are intentionally omitted since the guard needs only the items.
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    unguarded = [
        item.nodeid for item in items if _is_write_gated(item) and item.get_closest_marker("live_write") is None
    ]
    if unguarded:
        raise pytest.UsageError(
            "write-gated tests are missing the live_write marker, so the #271 abort "
            "hook cannot protect them: " + ", ".join(unguarded)
        )
