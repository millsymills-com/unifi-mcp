"""Property tests for the error-classification helper.

PY-013 / MCP-013: every package ships at least one hypothesis-driven test
that pins down an invariant rather than an example. The classify helper is
a pure function over (status_code, exception type), so its output shape is
amenable to property checks.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiConnectionError,
    UniFiError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiServerError,
    UniFiTimeoutError,
)
from unifi_mcp.tools._error_adapter import _classify_error_tag

ERROR_CLASSES = (
    UniFiError,
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiServerError,
    UniFiTimeoutError,
    UniFiConnectionError,
)


@given(message=st.text(max_size=64), code=st.integers(min_value=100, max_value=599))
def test_classify_error_tag_contains_status_when_set(message: str, code: int) -> None:
    error = UniFiError(message, status_code=code)
    tag = _classify_error_tag(error)
    assert tag == f"[HTTP {code}] "


@given(message=st.text(max_size=64))
def test_classify_error_tag_is_empty_when_no_status(message: str) -> None:
    error = UniFiError(message)
    assert _classify_error_tag(error) == ""


@given(
    cls=st.sampled_from(ERROR_CLASSES),
    message=st.text(max_size=64),
    code=st.one_of(st.none(), st.integers(min_value=100, max_value=599)),
)
def test_classify_error_tag_does_not_raise_for_any_subclass(
    cls: type[UniFiError], message: str, code: int | None
) -> None:
    error = cls(message, status_code=code)
    tag = _classify_error_tag(error)
    assert isinstance(tag, str)
    assert tag.startswith("[HTTP ") or tag == ""
