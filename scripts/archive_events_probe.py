"""Find the correct endpoint/command for archive_events."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from unifi_mcp.clients.network import NetworkClient

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def main() -> None:
    api_key = os.environ.get("UNIFI_NETWORK_API")
    if not api_key:
        print("UNIFI_NETWORK_API not set", file=sys.stderr)
        sys.exit(2)

    host = os.environ.get("UNIFI_NETWORK_HOST", "192.168.1.1")
    verify_ssl = _bool_env("UNIFI_NETWORK_VERIFY_SSL")
    if not verify_ssl:
        print(f"WARNING: TLS verification disabled for {host} (probe script)", file=sys.stderr)

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
        # First, check what alarms exist.
        alarms = await client.get("rest/alarm")
        alarm_data = alarms.get("data", []) if isinstance(alarms, dict) else []
        archived = sum(1 for a in alarm_data if a.get("archived") is True)
        unarchived = sum(1 for a in alarm_data if not a.get("archived"))
        print(f"Current alarms: total={len(alarm_data)} archived={archived} unarchived={unarchived}")
        if alarm_data:
            sample = alarm_data[0]
            print(f"Sample alarm keys: {sorted(sample.keys())}")
            if "_id" in sample:
                print(f"Sample _id: {sample['_id']}")

        # Then probe candidates.
        candidates = [
            ("cmd/evtmgr", {"cmd": "archive-all-alarms"}),
            ("cmd/evtmgr", {"cmd": "archive-alarm"}),
            ("cmd/evtmgr", {"cmd": "archive"}),
            ("cmd/notification", {"cmd": "archive-all-alarms"}),
            ("cmd/alarmmgr", {"cmd": "archive-all-alarms"}),
            ("cmd/sitemgr", {"cmd": "archive-all-alarms"}),
            ("cmd/alarm", {"cmd": "archive-all-alarms"}),
            ("cmd/system", {"cmd": "archive-all-alarms"}),
            ("list/alarm", {}),
        ]

        for path, body in candidates:
            try:
                result = await client.post(path, json=body)
                summary = list(result.keys()) if isinstance(result, dict) else type(result).__name__
                print(f"OK    POST {path} {body}  -> keys={summary}")
            except Exception as exc:
                print(f"FAIL  POST {path} {body}  -> {exc}")
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
