"""One-off probe: discover the create_route payload shape the controller accepts."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from typing import Any

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.errors import UniFiBadRequestError

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def _read_and_cleanup_route(
    client: NetworkClient, route_id: str, name: str, label: str, payload: dict[str, Any]
) -> None:
    route_error: BaseException | None = None
    try:
        print(f"{label}: ACCEPTED (id={route_id})")
        print(f"    payload was: {payload}")
        print("    read-back:")
        rb = await client.get_route(route_id)
        for k, v in (rb.get("data") or [{}])[0].items():
            print(f"      {k}: {v}")
    except BaseException as exc:
        route_error = exc
        exc.add_note(f"Read-back or output failed for probe route {route_id} (name={name}).")
        raise
    finally:
        try:
            await client.delete_route(route_id)
        except BaseException as cleanup_error:
            recovery = f"Failed to delete probe route {route_id} (name={name}); manual cleanup required"
            cleanup_error.add_note(recovery)
            logger.error("%s: %s", recovery, cleanup_error)
            if route_error is None:
                raise
            route_error.add_note(f"{recovery}: {cleanup_error!r}")


async def main() -> None:
    api_key = os.environ.get("UNIFI_NETWORK_API")
    if not api_key:
        print("UNIFI_NETWORK_API not set", file=sys.stderr)
        sys.exit(2)

    host = os.environ.get("UNIFI_NETWORK_HOST", "192.168.1.1")
    verify_ssl = _bool_env("UNIFI_NETWORK_VERIFY_SSL")
    if not verify_ssl:
        print(f"WARNING: TLS verification disabled for {host} (probe script)", file=sys.stderr)

    suffix = uuid.uuid4().hex[:6]
    name = f"probe-route-{suffix}"

    candidates = [
        {
            "label": "type=static-route + prefixed",
            "data": {
                "name": name,
                "type": "static-route",
                "enabled": False,
                "static-route_network": "10.99.250.0/24",
                "static-route_distance": 1,
                "static-route_type": "nexthop-route",
                "static-route_nexthop": "192.168.1.1",
            },
        },
        {
            "label": "type=static-route + prefixed, no distance",
            "data": {
                "name": name,
                "type": "static-route",
                "enabled": False,
                "static-route_network": "10.99.250.0/24",
                "static-route_type": "nexthop-route",
                "static-route_nexthop": "192.168.1.1",
            },
        },
        {
            "label": "type=nexthop-route at top + prefixed",
            "data": {
                "name": name,
                "type": "nexthop-route",
                "enabled": False,
                "static-route_network": "10.99.250.0/24",
                "static-route_nexthop": "192.168.1.1",
            },
        },
    ]

    client = NetworkClient(
        base_url=f"https://{host}:443",
        api_key=api_key,
        site=os.environ.get("UNIFI_NETWORK_SITE", "default"),
        verify_ssl=verify_ssl,
        timeout=15,
        max_retries=1,
    )

    primary_error: BaseException | None = None
    try:
        for i, cand in enumerate(candidates):
            try:
                result = await client.create_route(cand["data"])
            except UniFiBadRequestError as exc:
                if exc.status_code != 400:
                    exc.add_note(f"Create outcome indeterminate for {name}; inspect the controller before retrying.")
                    raise
                print(f"[{i}] {cand['label']}: REJECTED — {exc}")
                continue
            except BaseException as exc:
                exc.add_note(f"Create outcome indeterminate for {name}; inspect the controller before retrying.")
                raise

            data = result.get("data") if isinstance(result, dict) else None
            route_id = (
                data[0].get("_id") if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict) else None
            )
            if not isinstance(route_id, str) or not route_id.strip():
                raise RuntimeError(
                    f"Create outcome indeterminate for {name}: no unique usable route ID; "
                    "inspect the controller before retrying."
                )

            await _read_and_cleanup_route(client, route_id, name, f"[{i}] {cand['label']}", cand["data"])
            print("    cleaned up.")
            return
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            await client.close()
        except BaseException as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note(f"Client closure also failed: {cleanup_error!r}")
            logger.warning("Client closure also failed: %s", cleanup_error)


if __name__ == "__main__":
    asyncio.run(main())
