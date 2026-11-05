"""End-to-end sanity checks that pin down the mode/availability contract.

Closes three of the tractable sub-items in #97's audit inventory:

* §3e  — readonly mode must hide *every* write-tagged tool, not just a
          hand-picked subset (current tests only spot-check 4-6 names).
* §3d  — per-API graceful degradation: each combination (Network-only /
          Protect-only / Site-Manager-only) yields exactly the
          corresponding namespace on the tool list.
* §2a  — bad-auth generalization: #87's tag-disable fix applies to every
          API, not just Protect. Assert for Network and Site Manager.

All tests use stubs — no live hardware.
"""

from __future__ import annotations

from contextlib import ExitStack, aclosing
from unittest.mock import AsyncMock, patch

import pytest

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server, server_lifespan

# ── §3e: readonly hides every write tool ───────────────────────────────────


class TestReadonlyHidesEveryWriteTool:
    """#97 §3e: a regression-proof enumeration of the readonly gate.

    Builds a server in readonly mode with all three API keys set and
    asserts that the only tools in ``list_tools()`` whose tags contain
    ``write`` is the empty set.
    """

    async def test_no_write_tool_visible_in_readonly(self):
        cfg = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READONLY,
            unifi_network_api="net",
            unifi_protect_api="prot",
            unifi_site_manager_api="sm",
        )
        server = create_server(cfg)
        tools = await server.list_tools()
        leaking = [t.name for t in tools if "write" in set(t.tags)]
        assert leaking == [], f"Readonly mode is leaking write tools: {leaking}"

    async def test_every_tool_carries_the_unifi_namespace(self):
        """PROTO-002: every registered tool must start with ``unifi_``."""
        cfg = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
            unifi_network_api="net",
            unifi_protect_api="prot",
            unifi_site_manager_api="sm",
        )
        server = create_server(cfg)
        bad = [t.name for t in await server.list_tools() if not t.name.startswith("unifi_")]
        assert bad == [], f"Tools without unifi_ namespace prefix: {bad}"

    async def test_every_registered_write_tool_is_restorable_in_readwrite(self):
        """The inverse: the readwrite set minus the readonly set equals
        exactly the tools tagged ``write``. Proves the gate neither hides
        extra tools nor leaves any write tool behind.
        """
        kwargs = {
            "_env_file": None,
            "unifi_network_api": "net",
            "unifi_protect_api": "prot",
            "unifi_site_manager_api": "sm",
        }
        ro = create_server(UniFiConfig(unifi_mode=UniFiMode.READONLY, **kwargs))
        rw = create_server(UniFiConfig(unifi_mode=UniFiMode.READWRITE, **kwargs))

        ro_names = {t.name for t in await ro.list_tools()}
        rw_tools = await rw.list_tools()

        exclusive_to_rw = {t.name for t in rw_tools} - ro_names
        write_tagged = {t.name for t in rw_tools if "write" in set(t.tags)}
        # Without this, the equality below trivially passes when both sets
        # are empty — a refactor that strips every {"write"} tag would leak.
        assert write_tagged, "expected at least one write-tagged tool; tag wiring may be broken"
        assert exclusive_to_rw == write_tagged, (
            "Difference between readwrite and readonly tool sets must equal "
            "exactly the write-tagged tools.\n"
            f"  diff: {sorted(exclusive_to_rw)}\n"
            f"  write-tagged: {sorted(write_tagged)}"
        )


# ── Shared helpers for the lifespan-driven tests ──────────────────────────


def _clear_api_env(monkeypatch, tmp_path) -> None:
    """Clear API env vars and isolate from any ``.env`` in cwd.

    ``UniFiConfig`` reads ``.env`` via pydantic-settings' ``env_file`` option,
    so ``monkeypatch.delenv`` alone doesn't prevent a contributor's real
    ``.env`` (or one placed at repo root) from leaking API keys into the
    test. Chdir to a tmp path that has no ``.env``.
    """
    for var in ("UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNIFI_NETWORK_INTEGRATION_ENABLED", "false")


def _stub_client(valid: bool = True) -> AsyncMock:
    client = AsyncMock()
    client.validate_connection.return_value = valid
    return client


# ── §3d: per-API degradation matrix ────────────────────────────────────────


class TestDegradationMatrix:
    """#97 §3d: for each single-API configuration, only that API's tools are
    visible in ``list_tools()``. The configured-but-unreachable APIs' tools
    are hidden by the #87 tag-disable path; never-configured APIs aren't
    registered in the first place.
    """

    @pytest.mark.parametrize(
        ("env_key", "expected_prefix"),
        [
            ("UNIFI_NETWORK_API", "unifi_network_"),
            ("UNIFI_PROTECT_API", "unifi_protect_"),
            ("UNIFI_SITE_MANAGER_API", "unifi_site_manager_"),
        ],
    )
    async def test_single_api_exposes_only_its_namespace(self, monkeypatch, tmp_path, env_key, expected_prefix):
        _clear_api_env(monkeypatch, tmp_path)
        monkeypatch.setenv(env_key, "k")
        monkeypatch.setenv("UNIFI_MODE", "readonly")

        server = create_server()
        # Patch whichever client class matches the configured API.
        client_patches = {
            "UNIFI_NETWORK_API": "unifi_mcp.clients.network.NetworkClient",
            "UNIFI_PROTECT_API": "unifi_mcp.clients.protect.ProtectClient",
            "UNIFI_SITE_MANAGER_API": "unifi_mcp.clients.site_manager.SiteManagerClient",
        }
        with ExitStack() as stack:
            stack.enter_context(patch(client_patches[env_key], return_value=_stub_client(True)))
            gen = server_lifespan._fn(server)
            async with aclosing(gen):
                await gen.__anext__()
                names = {t.name for t in await server.list_tools()}
                other_prefixes = {"unifi_network_", "unifi_protect_", "unifi_site_manager_"} - {expected_prefix}
                leaks = [n for n in names if any(n.startswith(p) for p in other_prefixes)]
                assert not leaks, f"{env_key}-only config leaks foreign tools: {leaks}"
                assert any(n.startswith(expected_prefix) for n in names)
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

    async def test_no_apis_configured_yields_empty_tool_set(self, monkeypatch, tmp_path):
        _clear_api_env(monkeypatch, tmp_path)
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        server = create_server()
        gen = server_lifespan._fn(server)
        async with aclosing(gen):
            await gen.__anext__()
            names = {t.name for t in await server.list_tools()}
            assert names == set(), f"Expected zero tools with no APIs configured, got {sorted(names)}"
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()


# ── §2a: bad-auth generalization for Network + Site Manager ────────────────


class TestBadAuthDisablesAnyAPI:
    """#97 §2a: when any API's ``validate_connection`` fails, that API's
    tools are disabled. The existing test_unreachable_api_disables_its_tools
    only covers Protect; this parametrises over all three.
    """

    @pytest.mark.parametrize(
        ("failing_api", "prefix"),
        [
            ("network", "unifi_network_"),
            ("protect", "unifi_protect_"),
            ("site_manager", "unifi_site_manager_"),
        ],
    )
    async def test_failing_api_tools_disabled(self, monkeypatch, failing_api, prefix):
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        monkeypatch.setenv("UNIFI_NETWORK_INTEGRATION_ENABLED", "false")
        monkeypatch.setenv("UNIFI_NETWORK_API", "n")
        monkeypatch.setenv("UNIFI_PROTECT_API", "p")
        monkeypatch.setenv("UNIFI_SITE_MANAGER_API", "s")

        server = create_server()
        net = _stub_client(failing_api != "network")
        prot = _stub_client(failing_api != "protect")
        sm = _stub_client(failing_api != "site_manager")

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=sm),
        ):
            gen = server_lifespan._fn(server)
            async with aclosing(gen):
                await gen.__anext__()
                names = {t.name for t in await server.list_tools()}
                assert not any(n.startswith(prefix) for n in names), (
                    f"Failing {failing_api} API still exposes tools: {sorted(n for n in names if n.startswith(prefix))}"
                )
                # Sanity: the two healthy APIs' tools remain visible.
                other_prefixes = {"unifi_network_", "unifi_protect_", "unifi_site_manager_"} - {prefix}
                for other in other_prefixes:
                    assert any(n.startswith(other) for n in names), f"Healthy API '{other}' unexpectedly hidden"
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()
