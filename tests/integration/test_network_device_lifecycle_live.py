"""Live Network device-lifecycle tests: adopt / forget / upgrade.

These are the riskiest write tools in the Network surface — a botched
forget+adopt cycle can leave a device unadopted (loses controller config,
requires manual reset to recover) and ``upgrade_device`` initiates a firmware
flash that takes minutes and can soft-brick on interruption.

Each test is gated behind its own env var so they can be run individually:

- ``LIVE_TEST_FORGET_ADOPT=1`` enables the forget→adopt cycle
- ``LIVE_TEST_UPGRADE=1`` enables the upgrade smoke test

Required env vars (same as other device-ops tests):
- ``UNIFI_MCP_TEST_PROTECTED_MACS`` — fail-fast allowlist
- ``UNIFI_MCP_TEST_TARGET_MAC`` — non-WAP, non-gateway device to cycle
- ``UNIFI_MCP_TEST_RISKY_TARGET_MAC`` (optional) — overrides for risky cycle only

Run individually:
    LIVE_TEST_FORGET_ADOPT=1 \\
    UNIFI_MCP_TEST_PROTECTED_MACS=<wap>,<gw> \\
    UNIFI_MCP_TEST_TARGET_MAC=<test device MAC> \\
        uv run pytest tests/integration/test_network_device_lifecycle_live.py -v -m integration
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

from tests.integration.conftest import _normalize_mac

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _find_device(devices: dict, mac: str) -> dict | None:
    return next(
        (d for d in devices.get("data", []) if (d.get("mac") or "").lower() == mac.lower()),
        None,
    )


def _risky_target_mac() -> str:
    """Use UNIFI_MCP_TEST_RISKY_TARGET_MAC if set, else fall back to UNIFI_MCP_TEST_TARGET_MAC."""
    return (
        os.environ.get("UNIFI_MCP_TEST_RISKY_TARGET_MAC", "").strip().lower()
        or os.environ.get("UNIFI_MCP_TEST_TARGET_MAC", "").strip().lower()
    )


_READOPT_TIMEOUT_S = 180.0
_READOPT_POLL_INTERVAL_S = 5.0


async def _wait_for_adopted(client, mac: str, deadline: float) -> bool:
    """Poll list_devices() until ``mac`` reports adopted=True or deadline expires."""
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(_READOPT_POLL_INTERVAL_S)
        devices = await client.list_devices()
        target = _find_device(devices, mac)
        if target and target.get("adopted"):
            return True
    return False


async def _wait_for_pending_then_adopt(client, mac: str, deadline: float) -> bool:
    """Wait for ``mac`` to surface as un-adopted post-forget, issue adopt, wait for adopted state."""
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(_READOPT_POLL_INTERVAL_S)
        devices = await client.list_devices()
        target = _find_device(devices, mac)
        if target is None:
            continue
        if target.get("adopted"):
            LOG.warning("%s adopted again before adopt_device was called (likely auto-adopt).", mac)
            return True
        try:
            adopt_response = await client.adopt_device(mac)
            assert isinstance(adopt_response, dict), "adopt_device must return a dict"
            LOG.warning("adopt_device(%s) issued; waiting for adoption to complete...", mac)
        except Exception as exc:
            LOG.warning("adopt_device(%s) failed: %s", mac, exc)
            continue
        return await _wait_for_adopted(client, mac, deadline)
    return False


@pytest.mark.skipif(
    not _enabled("LIVE_TEST_FORGET_ADOPT"),
    reason="Set LIVE_TEST_FORGET_ADOPT=1 to run the forget→adopt cycle (irreversible if cleanup fails)",
)
class TestForgetAdoptCycle:
    """Forget → wait for pending-adoption → adopt round-trip.

    The cycle takes ~30-180s depending on how fast the device re-broadcasts
    after a forget. On failure, the test logs the device state so an operator
    can manually recover.
    """

    async def test_forget_adopt_cycle(self, network_live_client, protected_macs, cleanup_register):
        mac = _risky_target_mac()
        if not mac:
            pytest.skip("UNIFI_MCP_TEST_TARGET_MAC or UNIFI_MCP_TEST_RISKY_TARGET_MAC unset")
        assert _normalize_mac(mac) not in protected_macs, f"{mac} is in protected_macs; refusing to cycle"

        devices_before = await network_live_client.list_devices()
        target = _find_device(devices_before, mac)
        if target is None:
            pytest.skip(f"Target MAC {mac} not in device list")
        if not target.get("adopted"):
            pytest.skip(f"Target MAC {mac} is not currently adopted; nothing to forget")

        LOG.warning(
            "forget_adopt cycle starting against %s (%s, %s)",
            mac,
            target.get("name"),
            target.get("model"),
        )

        forget_response = await network_live_client.forget_device(mac)
        assert isinstance(forget_response, dict), "forget_device must return a dict"
        cleanup_register(network_live_client.adopt_device, mac)

        try:
            deadline = asyncio.get_event_loop().time() + _READOPT_TIMEOUT_S
            adopted_again = await _wait_for_pending_then_adopt(network_live_client, mac, deadline)

            if not adopted_again:
                LOG.error(
                    "forget_adopt cycle: %s did not return to adopted state within %ss — "
                    "issuing final best-effort adopt_device to limit blast radius.",
                    mac,
                    _READOPT_TIMEOUT_S,
                )
                try:
                    await network_live_client.adopt_device(mac)
                except Exception as exc:
                    LOG.error("Final recovery adopt_device(%s) also failed: %s. Manual recovery required.", mac, exc)

            assert adopted_again, (
                f"forget_adopt cycle: {mac} did not return to adopted state within {_READOPT_TIMEOUT_S}s. "
                "Manual recovery may be required."
            )
        except Exception:
            devices_final = await network_live_client.list_devices()
            target_final = _find_device(devices_final, mac)
            LOG.error(
                "forget_adopt cycle aborted; %s final state: adopted=%s, state=%s",
                mac,
                target_final.get("adopted") if target_final else None,
                target_final.get("state") if target_final else None,
            )
            if target_final is not None and not target_final.get("adopted"):
                try:
                    await network_live_client.adopt_device(mac)
                    LOG.warning("Best-effort recovery adopt_device(%s) issued.", mac)
                except Exception as recovery_exc:
                    LOG.error("Recovery adopt_device(%s) failed: %s", mac, recovery_exc)
            raise


@pytest.mark.skipif(
    not _enabled("LIVE_TEST_UPGRADE"),
    reason="Set LIVE_TEST_UPGRADE=1 to run upgrade_device smoke test (~5min, risk of soft-brick)",
)
class TestUpgradeDevice:
    """``upgrade_device`` smoke test.

    Initiates a firmware upgrade. If the device is already on the latest
    firmware, the controller may return success and no-op, or may surface
    a typed error. Either is informative — we assert response shape only
    and do not wait for the upgrade to complete.
    """

    async def test_upgrade_device(self, network_live_client, protected_macs):
        mac = _risky_target_mac()
        if not mac:
            pytest.skip("UNIFI_MCP_TEST_TARGET_MAC or UNIFI_MCP_TEST_RISKY_TARGET_MAC unset")
        assert _normalize_mac(mac) not in protected_macs

        devices = await network_live_client.list_devices()
        target = _find_device(devices, mac)
        if target is None:
            pytest.skip(f"Target MAC {mac} not in device list")

        LOG.warning(
            "upgrade_device(%s) — device may flash firmware. Currently: %s (%s) fw=%s",
            mac,
            target.get("name"),
            target.get("model"),
            target.get("version"),
        )

        response = await network_live_client.upgrade_device(mac)
        assert isinstance(response, dict), "upgrade_device must return a dict"
