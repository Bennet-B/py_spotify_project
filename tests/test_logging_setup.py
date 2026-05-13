from __future__ import annotations

import logging

import pytest

from spotify_project.logging_setup import RedactAuthFilter, configure_logging


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("raw_message", "sensitive_fragment"),
    [
        # Bearer access token (URL-safe chars after the "Bearer " prefix).
        ("Authorization: Bearer abc123-XYZ_456", "abc123-XYZ_456"),
        # Basic auth — base64 with padding, covers the +/= alphabet distinctively.
        ("Authorization: Basic MTZjMDU3YWM1ZWQ4NGM3ZGI3MQ==", "MTZjMDU3"),
        # OAuth refresh token in a single-quoted dict body (how `requests` debug logs format them).
        ("Body: {'refresh_token': 'AQCDDZyoMcDmoyCACYueXoNRcmkP', 'grant_type': 'refresh_token'}", "AQCDDZyo"),
    ],
    ids=["bearer", "basic_auth", "refresh_token"],
)
def test_redact_filter_scrubs_secrets(raw_message: str, sensitive_fragment: str) -> None:
    """RedactAuthFilter removes the sensitive fragment from the message and substitutes the placeholder."""
    record = _make_record(raw_message)
    RedactAuthFilter().filter(record)
    assert sensitive_fragment not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_redact_filter_scrubs_multiple_secrets_in_one_message() -> None:
    """Two distinct credential patterns in one message both get redacted (regex sub finds all non-overlapping matches)."""
    record = _make_record("Authorization: Bearer tokenABC and Authorization: Basic dXNlcjpwYXNz")
    RedactAuthFilter().filter(record)
    message = record.getMessage()
    assert "tokenABC" not in message
    assert "dXNlcjpwYXNz" not in message
    assert message.count("***REDACTED***") == 2


def test_redact_filter_leaves_innocent_messages_alone() -> None:
    msg = "Fetching playlist 3v8PWRLiPHGPY0oHgkoZvV (20 tracks)"
    record = _make_record(msg)
    RedactAuthFilter().filter(record)
    assert record.getMessage() == msg


def test_redact_filter_always_returns_true() -> None:
    """Filter must keep the record (return True), only redact in place."""
    assert RedactAuthFilter().filter(_make_record("anything")) is True
    assert RedactAuthFilter().filter(_make_record("Bearer secret")) is True


def test_configure_logging_sets_split_levels() -> None:
    configure_logging(app_level="DEBUG", third_party_level="ERROR")
    assert logging.getLogger("spotify_project").level == logging.DEBUG
    # third-party = root level
    assert logging.getLogger().level == logging.ERROR


def test_configure_logging_attaches_redact_filter() -> None:
    configure_logging()
    filters = logging.getLogger().filters
    assert any(isinstance(f, RedactAuthFilter) for f in filters)
