"""Per-method coverage for NetworkClient methods not covered in test_network.py (#72)."""

from __future__ import annotations

import httpx
import pytest
import respx

from unifi_mcp.clients.network import NetworkClient

BASE_URL = "https://10.0.0.1:443"
SITE = "default"
API_PREFIX = f"{BASE_URL}/proxy/network/api/s/{SITE}/"


@pytest.fixture
def client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site=SITE, timeout=5, max_retries=1)


class TestReadMethods:
    @respx.mock
    async def test_list_events_applies_limit(self, client):
        route = respx.get(f"{API_PREFIX}list/alarm").mock(return_value=httpx.Response(200, json={"data": []}))
        await client.list_events(limit=50)
        assert route.calls[0].request.url.params["_limit"] == "50"

    @respx.mock
    async def test_list_devices_basic(self, client):
        respx.get(f"{API_PREFIX}stat/device-basic").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_devices_basic() == {"data": []}

    @respx.mock
    async def test_list_configured_clients(self, client):
        respx.get(f"{API_PREFIX}rest/user").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_configured_clients() == {"data": []}

    @respx.mock
    async def test_list_all_clients(self, client):
        route = respx.get(f"{API_PREFIX}stat/alluser").mock(return_value=httpx.Response(200, json={"data": []}))
        await client.list_all_clients()
        assert route.calls[0].request.url.params["type"] == "all"
        assert route.calls[0].request.url.params["conn"] == "all"

    @respx.mock
    async def test_get_dpi_stats(self, client):
        route = respx.get(f"{API_PREFIX}stat/dpi").mock(return_value=httpx.Response(200, json={"data": []}))
        await client.get_dpi_stats(dpi_type="by_cat")
        assert route.calls[0].request.url.params["type"] == "by_cat"

    @respx.mock
    async def test_get_sysinfo(self, client):
        respx.get(f"{API_PREFIX}stat/sysinfo").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_sysinfo() == {"data": []}

    @respx.mock
    async def test_get_wlan(self, client):
        respx.get(f"{API_PREFIX}rest/wlanconf/w-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_wlan("w-1") == {"data": []}

    @respx.mock
    async def test_list_networks(self, client):
        respx.get(f"{API_PREFIX}rest/networkconf").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_networks() == {"data": []}

    @respx.mock
    async def test_get_network(self, client):
        respx.get(f"{API_PREFIX}rest/networkconf/n-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_network("n-1") == {"data": []}

    @respx.mock
    async def test_list_firewall_rules(self, client):
        respx.get(f"{API_PREFIX}rest/firewallrule").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_firewall_rules() == {"data": []}

    @respx.mock
    async def test_get_firewall_rule(self, client):
        respx.get(f"{API_PREFIX}rest/firewallrule/r-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_firewall_rule("r-1") == {"data": []}

    @respx.mock
    async def test_list_firewall_groups(self, client):
        respx.get(f"{API_PREFIX}rest/firewallgroup").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_firewall_groups() == {"data": []}

    @respx.mock
    async def test_get_firewall_group(self, client):
        respx.get(f"{API_PREFIX}rest/firewallgroup/g-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_firewall_group("g-1") == {"data": []}

    @respx.mock
    async def test_list_port_forwards(self, client):
        respx.get(f"{API_PREFIX}rest/portforward").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_port_forwards() == {"data": []}

    @respx.mock
    async def test_get_port_forward(self, client):
        respx.get(f"{API_PREFIX}rest/portforward/pf-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_port_forward("pf-1") == {"data": []}

    @respx.mock
    async def test_list_routes(self, client):
        respx.get(f"{API_PREFIX}rest/routing").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.list_routes() == {"data": []}

    @respx.mock
    async def test_get_route(self, client):
        respx.get(f"{API_PREFIX}rest/routing/r-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_route("r-1") == {"data": []}

    @respx.mock
    async def test_get_settings(self, client):
        respx.get(f"{API_PREFIX}rest/setting").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await client.get_settings() == {"data": []}


class TestCrudMethods:
    @pytest.mark.parametrize(
        ("method_name", "endpoint", "verb"),
        [
            ("create_network", "rest/networkconf", "post"),
            ("create_firewall_rule", "rest/firewallrule", "post"),
            ("create_firewall_group", "rest/firewallgroup", "post"),
            ("create_port_forward", "rest/portforward", "post"),
            ("create_route", "rest/routing", "post"),
        ],
    )
    @respx.mock
    async def test_create_posts(self, client, method_name, endpoint, verb):
        route = getattr(respx, verb)(f"{API_PREFIX}{endpoint}").mock(return_value=httpx.Response(200, json={}))
        await getattr(client, method_name)({"name": "x"})
        assert route.call_count == 1
        assert b"name" in route.calls[0].request.content

    @pytest.mark.parametrize(
        ("method_name", "endpoint"),
        [
            ("update_network", "rest/networkconf"),
            ("update_firewall_rule", "rest/firewallrule"),
            ("update_firewall_group", "rest/firewallgroup"),
            ("update_port_forward", "rest/portforward"),
            ("update_route", "rest/routing"),
        ],
    )
    @respx.mock
    async def test_update_puts_with_id(self, client, method_name, endpoint):
        route = respx.put(f"{API_PREFIX}{endpoint}/abc").mock(return_value=httpx.Response(200, json={}))
        await getattr(client, method_name)("abc", {"enabled": False})
        assert route.call_count == 1

    @pytest.mark.parametrize(
        ("method_name", "endpoint"),
        [
            ("delete_network", "rest/networkconf"),
            ("delete_firewall_rule", "rest/firewallrule"),
            ("delete_firewall_group", "rest/firewallgroup"),
            ("delete_port_forward", "rest/portforward"),
            ("delete_route", "rest/routing"),
        ],
    )
    @respx.mock
    async def test_delete_returns_empty_on_204(self, client, method_name, endpoint):
        route = respx.delete(f"{API_PREFIX}{endpoint}/abc").mock(return_value=httpx.Response(204))
        assert await getattr(client, method_name)("abc") == {}
        assert route.call_count == 1

    @respx.mock
    async def test_update_settings_dispatches_per_section(self, client):
        ntp_route = respx.put(f"{API_PREFIX}rest/setting/ntp").mock(return_value=httpx.Response(200, json={}))
        mgmt_route = respx.put(f"{API_PREFIX}rest/setting/mgmt").mock(return_value=httpx.Response(200, json={}))
        await client.update_settings({"ntp": {"ntp_server_1": "time.example.com"}, "mgmt": {"led_enabled": False}})
        assert ntp_route.call_count == 1
        assert mgmt_route.call_count == 1

    @respx.mock
    async def test_update_settings_partial_failure_does_not_rollback(self, client):
        """If section N's PUT fails, sections 1..N-1 stay applied (#225).

        Regression guard for the documented atomicity gap. The test relies on
        dict insertion-order iteration (Python 3.7+) to guarantee ``ntp`` is
        dispatched before ``mgmt`` — a future Python upgrade must preserve
        this property or this test (and the underlying contract) needs
        revisiting.
        """
        ntp_route = respx.put(f"{API_PREFIX}rest/setting/ntp").mock(
            return_value=httpx.Response(200, json={"meta": {"rc": "ok"}}),
        )
        mgmt_route = respx.put(f"{API_PREFIX}rest/setting/mgmt").mock(
            return_value=httpx.Response(500, json={"meta": {"rc": "error"}}),
        )

        from unifi_mcp.errors import UniFiServerError

        with pytest.raises(UniFiServerError):
            await client.update_settings({"ntp": {"ntp_server_1": "x"}, "mgmt": {"led_enabled": False}})
        assert ntp_route.call_count == 1, "first section must have been applied before the second failed"
        assert mgmt_route.call_count >= 1

    @respx.mock
    async def test_update_settings_rejects_non_dict_section(self, client):
        """A section whose value is not a dict is rejected before any PUT —
        each section body must be a partial-config mapping. The raised error
        names the offending section and the type seen.
        """
        from unifi_mcp.errors import UniFiError

        put_route = respx.put(f"{API_PREFIX}rest/setting/ntp").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(UniFiError, match="section 'ntp' must be a dict body, got str"):
            await client.update_settings({"ntp": "notadict"})
        assert put_route.call_count == 0, "validation must short-circuit before issuing the PUT"

    async def test_update_settings_rejects_empty_body(self, client):
        """An empty mapping carries no sections to dispatch — raise rather than
        silently no-op so the caller learns the request was meaningless. No HTTP
        is issued.
        """
        from unifi_mcp.errors import UniFiError

        with pytest.raises(UniFiError, match="no sections in body"):
            await client.update_settings({})


class TestCommandMethods:
    @pytest.mark.parametrize(
        ("method_name", "endpoint", "expected_cmd"),
        [
            ("run_speedtest", "cmd/devmgr", b"speedtest"),
            ("create_backup", "cmd/backup", b"backup"),
            ("reset_dpi", "cmd/stat", b"reset-dpi"),
        ],
    )
    @respx.mock
    async def test_no_arg_command(self, client, method_name, endpoint, expected_cmd):
        route = respx.post(f"{API_PREFIX}{endpoint}").mock(return_value=httpx.Response(200, json={}))
        await getattr(client, method_name)()
        assert expected_cmd in route.calls[0].request.content

    @respx.mock
    async def test_create_backup_uses_long_timeout(self, client):
        """Regression for #89: cmd/backup must carry a per-request timeout
        bump so the 30s default doesn't kill long-running backups.
        """
        route = respx.post(f"{API_PREFIX}cmd/backup").mock(return_value=httpx.Response(200, json={}))
        await client.create_backup()
        request = route.calls[0].request
        # httpx records timeouts via ext rather than public attrs, so assert on
        # httpx's internal read timeout on the Request extensions.
        timeout = request.extensions.get("timeout")
        assert timeout is not None
        # Every channel (connect/read/write/pool) should be at least 300s.
        for key, value in timeout.items():
            assert value is None or value >= 300.0, f"{key} timeout too short: {value}"

    @pytest.mark.parametrize(
        ("method_name", "endpoint", "expected_cmd", "precheck"),
        [
            # adopt_device now pre-checks stat/device to avoid the non-idempotent
            # api.err.InvalidTarget on already-adopted devices (#93).
            ("adopt_device", "cmd/devmgr", b"adopt", "device"),
            ("locate_device", "cmd/devmgr", b"set-locate", None),
            ("unlocate_device", "cmd/devmgr", b"unset-locate", None),
            ("provision_device", "cmd/devmgr", b"force-provision", None),
            ("upgrade_device", "cmd/devmgr", b"upgrade", None),
            # stamgr commands pre-check against the client list (#96).
            ("unblock_client", "cmd/stamgr", b"unblock-sta", "client"),
            ("kick_client", "cmd/stamgr", b"kick-sta", None),
            # unauthorize_guest additionally requires is_guest=True (#220).
            ("unauthorize_guest", "cmd/stamgr", b"unauthorize-guest", "guest"),
        ],
    )
    @respx.mock
    async def test_mac_command(self, client, method_name, endpoint, expected_cmd, precheck):
        mac = "aa:bb:cc:dd:ee:ff"
        if precheck == "client":
            respx.get(f"{API_PREFIX}stat/alluser").mock(
                return_value=httpx.Response(200, json={"data": [{"mac": mac}]}),
            )
        elif precheck == "guest":
            respx.get(f"{API_PREFIX}stat/alluser").mock(
                return_value=httpx.Response(200, json={"data": [{"mac": mac, "is_guest": True}]}),
            )
        elif precheck == "device":
            # Return empty device list so adopt proceeds (MAC not yet adopted).
            respx.get(f"{API_PREFIX}stat/device").mock(
                return_value=httpx.Response(200, json={"data": []}),
            )
        route = respx.post(f"{API_PREFIX}{endpoint}").mock(return_value=httpx.Response(200, json={}))
        await getattr(client, method_name)(mac)
        body = route.calls[0].request.content
        assert expected_cmd in body
        assert mac.encode() in body

    @respx.mock
    async def test_power_cycle_port_sends_port_idx(self, client):
        route = respx.post(f"{API_PREFIX}cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await client.power_cycle_port("aa:bb:cc:dd:ee:ff", 3)
        body = route.calls[0].request.content
        assert b"power-cycle" in body
        assert b'"port_idx":3' in body

    @respx.mock
    async def test_authorize_guest_sends_minutes(self, client):
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{API_PREFIX}stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "is_guest": True}]}),
        )
        route = respx.post(f"{API_PREFIX}cmd/stamgr").mock(return_value=httpx.Response(200, json={}))
        await client.authorize_guest(mac, minutes=90)
        body = route.calls[0].request.content
        assert b"authorize-guest" in body
        assert b"90" in body


class TestSilentNoOpProtection:
    """#96: the stamgr tools used to return meta.rc='ok' for unknown MACs,
    silently no-op'ing. Now they pre-check against list_all_clients and
    raise UniFiNotFoundError if the MAC is absent.
    """

    @pytest.mark.parametrize(
        "method_name",
        ["block_client", "unblock_client", "authorize_guest", "unauthorize_guest"],
    )
    @respx.mock
    async def test_unknown_mac_raises_not_found(self, client, method_name):
        # stat/alluser returns an empty list — MAC isn't known.
        respx.get(f"{API_PREFIX}stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": []}),
        )
        # The POST must never be reached.
        route = respx.post(f"{API_PREFIX}cmd/stamgr").mock(return_value=httpx.Response(200, json={}))

        from unifi_mcp.errors import UniFiNotFoundError

        with pytest.raises(UniFiNotFoundError, match="aa:bb:cc:dd:ee:ff"):
            await getattr(client, method_name)("aa:bb:cc:dd:ee:ff")
        assert route.call_count == 0

    @respx.mock
    async def test_kick_client_skips_precheck(self, client):
        """kick_client must NOT call stat/alluser — it relies on the controller's
        own validation so the behavior isn't coupled to active-client listings.
        """
        list_route = respx.get(f"{API_PREFIX}stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": []}),
        )
        respx.post(f"{API_PREFIX}cmd/stamgr").mock(return_value=httpx.Response(200, json={}))
        await client.kick_client("aa:bb:cc:dd:ee:ff")
        assert list_route.call_count == 0


class TestGuestOnlyProtection:
    """#220: authorize_guest / unauthorize_guest must reject non-guest MACs.

    The controller silently no-ops these commands on corp/non-guest clients
    (HTTP 200, meta.rc == "ok", but the active-client doc still reads
    authorized=True afterwards). Surface a typed error so agents see the
    no-op as a real failure.
    """

    @pytest.mark.parametrize("method_name", ["authorize_guest", "unauthorize_guest"])
    @respx.mock
    async def test_non_guest_mac_raises_bad_request(self, client, method_name):
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{API_PREFIX}stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "is_guest": False}]}),
        )
        post_route = respx.post(f"{API_PREFIX}cmd/stamgr").mock(return_value=httpx.Response(200, json={}))

        from unifi_mcp.errors import UniFiBadRequestError

        with pytest.raises(UniFiBadRequestError, match="not on a guest network"):
            await getattr(client, method_name)(mac)
        assert post_route.call_count == 0

    @pytest.mark.parametrize("method_name", ["authorize_guest", "unauthorize_guest"])
    @respx.mock
    async def test_missing_is_guest_field_raises_bad_request(self, client, method_name):
        """A client doc without ``is_guest`` (treated as False) is also rejected."""
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{API_PREFIX}stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac}]}),
        )
        post_route = respx.post(f"{API_PREFIX}cmd/stamgr").mock(return_value=httpx.Response(200, json={}))

        from unifi_mcp.errors import UniFiBadRequestError

        with pytest.raises(UniFiBadRequestError, match="not on a guest network"):
            await getattr(client, method_name)(mac)
        assert post_route.call_count == 0


class TestAdoptIdempotency:
    """#93 part 1: adopt_device must surface UniFiDeviceAlreadyAdoptedError
    when the MAC is already adopted, rather than letting the controller's
    opaque api.err.InvalidTarget 400 flow through.
    """

    @respx.mock
    async def test_already_adopted_raises_typed_error(self, client):
        from unifi_mcp.errors import UniFiDeviceAlreadyAdoptedError

        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{API_PREFIX}stat/device").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "adopted": True}]}),
        )
        # The POST must never be reached.
        post_route = respx.post(f"{API_PREFIX}cmd/devmgr").mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(UniFiDeviceAlreadyAdoptedError, match=mac):
            await client.adopt_device(mac)
        assert post_route.call_count == 0

    @respx.mock
    async def test_known_mac_not_yet_adopted_proceeds(self, client):
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{API_PREFIX}stat/device").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "adopted": False}]}),
        )
        post_route = respx.post(f"{API_PREFIX}cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await client.adopt_device(mac)
        assert post_route.call_count == 1
