from __future__ import annotations

import logging

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


def test_redact_filter_scrubs_bearer_token() -> None:
    record = _make_record("Authorization: Bearer abc123-XYZ_456")
    RedactAuthFilter().filter(record)
    assert "abc123-XYZ_456" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_redact_filter_scrubs_basic_auth() -> None:
    record = _make_record("Authorization: Basic MTZjMDU3YWM1ZWQ4NGM3ZGI3MQ==")
    RedactAuthFilter().filter(record)
    assert "MTZjMDU3" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_redact_filter_scrubs_refresh_token() -> None:
    record = _make_record("Body: {'refresh_token': 'AQCDDZyoMcDmoyCACYueXoNRcmkP', 'grant_type': 'refresh_token'}")
    RedactAuthFilter().filter(record)
    assert "AQCDDZyo" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


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
