"""Live block/unblock and authorize/unauthorize cycle tests (#43 §1a, #97 §1a).

These tests target the silent-success bug class for ``cmd/stamgr`` write tools:
``block_client``, ``unblock_client``, ``authorize_guest``, ``unauthorize_guest``.
The controller's legacy endpoints return HTTP 200 / ``meta.rc == "ok"`` regardless
of effect, so a unit test that only checks the response can't catch a no-op.
These cycle tests assert the post-state observably matches the intended effect.

Required env vars:

- ``UNIFI_NETWORK_API`` — Network-scoped API key (live controller).
- ``UNIFI_MCP_TEST_CLIENT_MAC`` — MAC of a client that is *currently active* on
  the controller and that may safely be blocked / unblocked / authorized.
  Consumed via the existing ``test_client_mac`` fixture in ``conftest.py``.

WARNING: blocking a MAC at the controller cuts that client's path through the
gateway. Do NOT set ``UNIFI_MCP_TEST_CLIENT_MAC`` to the wired MAC of the host
running pytest unless that host has an alternate path (e.g. WiFi) back to the
controller — otherwise the test will block its own runner mid-cycle and the
final cleanup unblock may not reach the controller. Prefer a different device's
MAC, or a host with a WiFi fallback.

Run manually:

    UNIFI_MCP_TEST_CLIENT_MAC=aa:bb:cc:dd:ee:ff \
        uv run pytest tests/integration/test_network_clients_live.py -v -m integration
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def _writes_enabled() -> bool:
    return os.environ.get("UNIFI_MODE", "readonly").lower() == "readwrite" and os.environ.get(
        "LIVE_TEST_WRITES", ""
    ).strip() in {"1", "true", "yes"}


WRITE_GATE_REASON = "Set UNIFI_MODE=readwrite and LIVE_TEST_WRITES=1 to run write tests"


_BLOCK_APPLY_DELAY_S = 2.0
_UNBLOCK_POLL_TIMEOUT_S = 15.0
_UNBLOCK_POLL_INTERVAL_S = 1.0
_AUTHORIZE_APPLY_DELAY_S = 2.0


def _active_macs(active_response: dict) -> set[str]:
    return {entry.get("mac", "").lower() for entry in active_response.get("data", [])}


def _find_active(active_response: dict, mac: str) -> dict | None:
    return next(
        (entry for entry in active_response.get("data", []) if entry.get("mac", "").lower() == mac),
        None,
    )


def _find_known(all_response: dict, mac: str) -> dict | None:
    return next(
        (entry for entry in all_response.get("data", []) if entry.get("mac", "").lower() == mac),
        None,
    )


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestBlockUnblockCycle:
    """Live block → verify → unblock → verify cycle.

    Verification approach: ``stat/sta`` (``list_active_clients``) only returns
    currently-connected clients, so a blocked client drops off that list. The
    historical ``stat/alluser`` view (``list_all_clients``) carries a
    ``blocked`` boolean. We assert disappearance from the active list as the
    primary signal and additionally check the ``blocked`` flag in
    ``list_all_clients`` when present — together this surfaces silent-success
    bugs where the API ack is fine but no state change occurred.
    """

    async def test_block_unblock_cycle(self, network_live_client, test_client_mac):
        mac = test_client_mac

        actives = await network_live_client.list_active_clients()
        if mac not in _active_macs(actives):
            pytest.skip(f"Target MAC {mac} not currently active; cannot test block cycle")

        try:
            block_response = await network_live_client.block_client(mac)
            assert isinstance(block_response, dict), "block_client must return a dict response"

            await asyncio.sleep(_BLOCK_APPLY_DELAY_S)

            after_block_active = await network_live_client.list_active_clients()
            active_after_block = mac in _active_macs(after_block_active)

            after_block_all = await network_live_client.list_all_clients()
            known = _find_known(after_block_all, mac)
            blocked_flag = known.get("blocked") if known is not None else None

            assert active_after_block is False or blocked_flag is True, (
                f"Block silent-success: MAC {mac} still active "
                f"(active={active_after_block}) and not flagged blocked (flag={blocked_flag!r}). "
                "block_client returned success but the controller state is unchanged."
            )

            unblock_response = await network_live_client.unblock_client(mac)
            assert isinstance(unblock_response, dict), "unblock_client must return a dict response"

            deadline = asyncio.get_event_loop().time() + _UNBLOCK_POLL_TIMEOUT_S
            reappeared = False
            cleared_flag = False
            while asyncio.get_event_loop().time() < deadline:
                actives_after_unblock = await network_live_client.list_active_clients()
                if mac in _active_macs(actives_after_unblock):
                    reappeared = True
                    break
                all_after_unblock = await network_live_client.list_all_clients()
                known_after = _find_known(all_after_unblock, mac)
                if known_after is not None and known_after.get("blocked") is False:
                    cleared_flag = True
                    break
                await asyncio.sleep(_UNBLOCK_POLL_INTERVAL_S)

            assert reappeared or cleared_flag, (
                f"Unblock silent-success: MAC {mac} neither reappeared in active list "
                f"nor had its blocked flag cleared within {_UNBLOCK_POLL_TIMEOUT_S}s."
            )
        finally:
            try:
                await network_live_client.unblock_client(mac)
            except Exception as exc:
                LOG.warning("Cleanup unblock_client(%s) failed: %s", mac, exc)


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestAuthorizeUnauthorizeCycle:
    """Live authorize_guest → verify → unauthorize_guest → verify cycle.

    Guest authorization is observable on active-client documents via the
    ``authorized`` boolean (controller-managed guest portal state). When the
    target client is not on a guest network the flag may not flip — in that
    case we still exercise the call path and surface any exception, which
    catches the silent-success bug at the write-call boundary even when the
    read surface is uninformative.
    """

    async def test_authorize_unauthorize_cycle(self, network_live_client, test_client_mac):
        mac = test_client_mac

        actives = await network_live_client.list_active_clients()
        entry = _find_active(actives, mac)
        if entry is None:
            pytest.skip(f"Target MAC {mac} not currently active; cannot test authorize cycle")
        if not entry.get("is_guest") and not entry.get("_is_guest_by_ugw") and not entry.get("_is_guest_by_usw"):
            pytest.skip(
                f"Target MAC {mac} is not on a guest network — authorize_guest is a no-op; "
                "set UNIFI_MCP_TEST_CLIENT_MAC to a guest-portal client to exercise this cycle."
            )

        try:
            authorize_response = await network_live_client.authorize_guest(mac, minutes=1)
            assert isinstance(authorize_response, dict), "authorize_guest must return a dict response"

            await asyncio.sleep(_AUTHORIZE_APPLY_DELAY_S)

            after_auth = await network_live_client.list_active_clients()
            entry_after_auth = _find_active(after_auth, mac)
            authorized_after = entry_after_auth.get("authorized") if entry_after_auth is not None else None
            if authorized_after is None:
                LOG.warning(
                    "authorize_guest verification: MAC %s missing or no 'authorized' field "
                    "on active-client doc; relying on write-call success only.",
                    mac,
                )
            else:
                assert authorized_after is True, (
                    f"Authorize silent-success: MAC {mac} active doc has authorized={authorized_after!r}; "
                    "expected True after authorize_guest."
                )

            unauthorize_response = await network_live_client.unauthorize_guest(mac)
            assert isinstance(unauthorize_response, dict), "unauthorize_guest must return a dict response"

            await asyncio.sleep(_AUTHORIZE_APPLY_DELAY_S)

            after_unauth = await network_live_client.list_active_clients()
            entry_after_unauth = _find_active(after_unauth, mac)
            if entry_after_unauth is not None and "authorized" in entry_after_unauth:
                assert entry_after_unauth.get("authorized") is False, (
                    f"Unauthorize silent-success: MAC {mac} active doc still authorized "
                    f"after unauthorize_guest (authorized={entry_after_unauth.get('authorized')!r})."
                )
        finally:
            try:
                await network_live_client.unauthorize_guest(mac)
            except Exception as exc:
                LOG.warning("Cleanup unauthorize_guest(%s) failed: %s", mac, exc)


_KICK_RECONNECT_TIMEOUT_S = 30.0
_KICK_POLL_INTERVAL_S = 1.5


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestKickClient:
    """Live kick_client smoke test.

    ``cmd/stamgr cmd=kick-sta`` is a wireless force-reauth. The controller
    accepts the call for wired clients too but it's effectively a no-op there.
    Either way we assert:

    1. The call returns a dict and does not raise (catches the
       UnknownStation / malformed-payload class of bug).
    2. If the client was wireless and dropped off active-list, that it
       reappears within the reconnect window (catches a permanent kick).
    """

    async def test_kick_client(self, network_live_client, test_client_mac):
        mac = test_client_mac

        actives = await network_live_client.list_active_clients()
        entry = _find_active(actives, mac)
        if entry is None:
            pytest.skip(f"Target MAC {mac} not currently active; cannot test kick")
        was_wired = bool(entry.get("is_wired"))

        response = await network_live_client.kick_client(mac)
        assert isinstance(response, dict), "kick_client must return a dict response"

        if was_wired:
            LOG.warning("kick_client target MAC %s is wired; kick-sta is effectively a no-op for wired STAs.", mac)
            return

        deadline = asyncio.get_event_loop().time() + _KICK_RECONNECT_TIMEOUT_S
        reappeared = False
        while asyncio.get_event_loop().time() < deadline:
            actives_now = await network_live_client.list_active_clients()
            if mac in _active_macs(actives_now):
                reappeared = True
                break
            await asyncio.sleep(_KICK_POLL_INTERVAL_S)

        assert reappeared, (
            f"kick_client target MAC {mac} never reappeared on active list "
            f"within {_KICK_RECONNECT_TIMEOUT_S}s — kick may be permanent (controller bug or wrong endpoint)."
        )
