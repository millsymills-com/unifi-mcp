"""Shared helpers for Network Integration read tools.

The Integration list endpoints return a paginated
``{data, offset, limit, count, totalCount}`` envelope. List tools expose
``offset``/``limit`` and bound them by ``unifi_max_list_offset`` /
``unifi_max_list_items`` before the client call, mirroring the legacy
list-tool caps so a prompt-injected agent cannot walk an unbounded cursor.
"""

from __future__ import annotations

from unifi_mcp.config import UniFiConfig
from unifi_mcp.errors import UniFiBadRequestError


def bound_pagination(config: UniFiConfig, *, offset: int, limit: int) -> None:
    """Reject ``offset``/``limit`` outside the configured ceilings.

    Args:
        config: The active server config carrying the ceilings.
        offset: Requested page offset.
        limit: Requested page size.

    Raises:
        UniFiBadRequestError: If ``offset`` is negative or above
            ``unifi_max_list_offset``, or ``limit`` is below 1 or above
            ``unifi_max_list_items``.
    """
    max_offset = config.unifi_max_list_offset
    max_items = config.unifi_max_list_items
    if not isinstance(offset, int) or offset < 0 or offset > max_offset:
        raise UniFiBadRequestError(f"offset must be between 0 and {max_offset} (got {offset!r})")
    if not isinstance(limit, int) or limit < 1 or limit > max_items:
        raise UniFiBadRequestError(f"limit must be between 1 and {max_items} (got {limit!r})")
