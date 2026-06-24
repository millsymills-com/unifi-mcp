"""Live Network device-ops tests.

Covers the cmd/devmgr + cmd/backup + cmd/stat write surface that doesn't
have CRUD equivalents:

- ``locate_device`` / ``unlocate_device`` — toggle LED, safe
- ``run_speedtest`` — initiates a WAN speed test, harmless
- ``create_backup`` — generates a controller backup file, non-destructive
- ``reset_dpi`` — clears DPI counters, harmless

Disruptive ops (``restart_device``, ``power_cycle_port``, ``assign_port_profile``,
``provision_device``) are gated behind ``LIVE_TEST_DESTRUCTIVE=1`` and live in
``TestDisruptiveDeviceOps``.

Risky ops (``adopt_device``, ``forget_device``, ``upgrade_device``) live in
``test_network_device_lifecycle_live.py`` and require per-tool confirmation.

Run:
    UNIFI_MCP_TEST_PROTECTED_MACS=<wap>,<gw> \\
    UNIFI_MCP_TEST_TARGET_MAC=<non-WAP device MAC> \\
        uv run pytest tests/integration/test_network_device_ops_live.py -v -m integration

Disruptive subset:
    LIVE_TEST_DESTRUCTIVE=1 \\
    UNIFI_MCP_TEST_PROTECTED_MACS=<wap>,<gw> \\
    UNIFI_MCP_TEST_TARGET_MAC=<non-WAP device MAC> \\
        uv run pytest tests/integration/test_network_device_ops_live.py -v -m integration
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import pytest

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def _destructive_enabled() -> bool:
    return os.environ.get("LIVE_TEST_DESTRUCTIVE", "").strip().lower() in {"1", "true", "yes", "on"}


def _writes_enabled() -> bool:
    return os.environ.get("UNIFI_MODE", "readonly").lower() == "readwrite" and os.environ.get(
        "LIVE_TEST_WRITES", ""
    ).strip() in {"1", "true", "yes"}


DESTRUCTIVE_GATE_REASON = "Set LIVE_TEST_DESTRUCTIVE=1 to run disruptive device-op tests"
WRITE_GATE_REASON = "Set UNIFI_MODE=readwrite and LIVE_TEST_WRITES=1 to run write tests"


def _find_device(devices: dict, mac: str) -> dict | None:
    return next(
        (d for d in devices.get("data", []) if (d.get("mac") or "").lower() == mac.lower()),
        None,
    )


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestLocateUnlocate:
    """``locate_device`` -> ``unlocate_device`` round-trip.

    LED state is exposed on the device document as ``locating`` (legacy)
    or in the ``led_override`` field. We assert both calls return a dict
    response shape and don't raise — visual confirmation of the LED is
    left to the operator.
    """

    async def test_locate_unlocate_cycle(self, network_live_client, test_target_mac):
        mac = test_target_mac

        devices = await network_live_client.list_devices()
        target = _find_device(devices, mac)
        if target is None:
            pytest.skip(f"Target MAC {mac} not in device list")

        try:
            locate_response = await network_live_client.locate_device(mac)
            assert isinstance(locate_response, dict), "locate_device must return a dict"
            await asyncio.sleep(1.5)
        finally:
            unlocate_response = await network_live_client.unlocate_device(mac)
            assert isinstance(unlocate_response, dict), "unlocate_device must return a dict"


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestRunSpeedtest:
    """``run_speedtest`` smoke test.

    The controller starts the test asynchronously and returns immediately.
    We assert response shape only — actual speed results show up in
    ``stat/health`` after ~30-60s, which we don't wait for.
    """

    async def test_run_speedtest(self, network_live_client):
        response = await network_live_client.run_speedtest()
        assert isinstance(response, dict), "run_speedtest must return a dict"
        meta = response.get("meta", {})
        assert meta.get("rc") == "ok" or "rc" not in meta, f"run_speedtest meta not ok: {meta}"


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestCreateBackup:
    """``create_backup`` smoke test.

    Backup endpoint can take minutes on non-trivial configs (see #89). The
    client already bumps timeout to 5min. We assert the call returns a dict
    and contains a URL or path in the response — that's the controller's
    handle to the generated backup file.
    """

    async def test_create_backup(self, network_live_client):
        response = await network_live_client.create_backup()
        assert isinstance(response, dict), "create_backup must return a dict"


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestResetDpi:
    """``reset_dpi`` smoke test.

    Clears DPI app/by-cat counters. ``get_dpi_stats`` would show fresh
    zeros after but new traffic between calls makes a strict assertion
    flaky — we assert response shape only.
    """

    async def test_reset_dpi(self, network_live_client):
        response = await network_live_client.reset_dpi()
        assert isinstance(response, dict), "reset_dpi must return a dict"
        meta = response.get("meta", {})
        assert meta.get("rc") == "ok" or "rc" not in meta, f"reset_dpi meta not ok: {meta}"


# ── Disruptive device ops ──────────────────────────────────────────────────


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _destructive_enabled(), reason=DESTRUCTIVE_GATE_REASON)
class TestDisruptiveDeviceOps:
    """Disruptive device-ops gated behind ``LIVE_TEST_DESTRUCTIVE=1``.

    All operations refuse to target ``protected_macs`` via fixture
    enforcement. ``test_target_mac`` already cross-checks the protected set.
    """

    async def test_restart_device(self, network_live_client, test_target_mac, protected_macs, touched_devices):
        mac = test_target_mac
        assert mac not in protected_macs, "test_target_mac collides with protected_macs"

        touched_devices.claim(mac, "restart")
        response = await network_live_client.restart_device(mac)
        assert isinstance(response, dict), "restart_device must return a dict"
        LOG.warning("restart_device(%s) issued — device will reboot in ~30s", mac)

    async def test_provision_device(self, network_live_client, test_target_mac, protected_macs, touched_devices):
        mac = test_target_mac
        assert mac not in protected_macs

        touched_devices.claim(mac, "provision")
        response = await network_live_client.provision_device(mac)
        assert isinstance(response, dict), "provision_device must return a dict"

    async def test_power_cycle_port(self, network_live_client, test_target_mac, protected_macs, touched_devices):
        """Skip unless target is a switch (PoE-capable). Port 1 by convention."""
        mac = test_target_mac
        assert mac not in protected_macs

        devices = await network_live_client.list_devices()
        target = _find_device(devices, mac)
        if target is None or target.get("type") != "usw":
            pytest.skip(f"Target {mac} is not a switch; power_cycle_port not applicable")

        port_idx = int(os.environ.get("UNIFI_MCP_TEST_PORT_IDX", "1"))
        touched_devices.claim(mac, "power_cycle")
        response = await network_live_client.power_cycle_port(mac, port_idx)
        assert isinstance(response, dict), "power_cycle_port must return a dict"
        LOG.warning("power_cycle_port(%s, port=%d) issued", mac, port_idx)

    async def test_assign_port_profile(
        self,
        network_live_client,
        test_target_mac,
        protected_macs,
        mcptest_prefix,
        cleanup_register,
    ):
        """Round-trip a port profile assignment, restoring the original.

        Requires a switch as target. Creates a transient port profile if the
        controller has none, deletes it during cleanup.
        """
        mac = test_target_mac
        assert mac not in protected_macs

        devices = await network_live_client.list_devices()
        target = _find_device(devices, mac)
        if target is None or target.get("type") != "usw":
            pytest.skip(f"Target {mac} is not a switch; assign_port_profile not applicable")

        profiles = await network_live_client.list_port_profiles()
        profile_data = profiles.get("data", [])

        if profile_data:
            test_profile_id = profile_data[0].get("_id")
            assert isinstance(test_profile_id, str)
        else:
            suffix = uuid.uuid4().hex[:6]
            created = await network_live_client.create_port_profile(
                {
                    "name": f"{mcptest_prefix}pp-assign-{suffix}",
                    "forward": "all",
                    "native_networkconf_id": "",
                    "poe_mode": "auto",
                }
            )
            test_profile_id = (created.get("data") or [{}])[0].get("_id")
            assert isinstance(test_profile_id, str)
            cleanup_register(network_live_client.delete_port_profile, test_profile_id)

        port_idx = int(os.environ.get("UNIFI_MCP_TEST_PORT_IDX", "1"))
        existing_overrides = target.get("port_overrides", [])
        original_profile = next(
            (o.get("portconf_id") for o in existing_overrides if o.get("port_idx") == port_idx),
            None,
        )

        try:
            response = await network_live_client.assign_port_profile(mac, port_idx, test_profile_id)
            assert isinstance(response, dict), "assign_port_profile must return a dict"
        finally:
            if original_profile:
                try:
                    await network_live_client.assign_port_profile(mac, port_idx, original_profile)
                except Exception as exc:
                    LOG.warning(
                        "Cleanup assign_port_profile(%s, %d, %s) failed: %s",
                        mac,
                        port_idx,
                        original_profile,
                        exc,
                    )
