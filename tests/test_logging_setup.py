from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from spotify_project.logging_setup import RedactAuthFilter, TqdmLoggingHandler, configure_logging


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    """Snapshot and restore process-wide logging state around configure_logging tests.

    configure_logging mutates the root logger (level, handlers) and the spotify_project logger level; without restoration, later tests become order-dependent.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_filters = root.filters[:]
    saved_level = root.level
    app_logger = logging.getLogger("spotify_project")
    saved_app_level = app_logger.level
    yield
    root.handlers[:] = saved_handlers
    root.filters[:] = saved_filters
    root.setLevel(saved_level)
    app_logger.setLevel(saved_app_level)


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
        # Access token in a repr-style OAuth response dump — followed by `'`, not whitespace, so the Bearer pattern alone can't catch it.
        ("Token: {'access_token': 'BQBwSecretAccessToken123', 'token_type': 'Bearer', 'expires_in': 3600}", "BQBwSecret"),
        # Double-quoted (JSON-style) body — both token kinds.
        ('Response: {"access_token": "BQBwSecretJson", "refresh_token": "AQCDSecretJson"}', "BQBwSecretJson"),
        ('Response: {"refresh_token": "AQCDSecretJson2"}', "AQCDSecretJson2"),
    ],
    ids=["bearer", "basic_auth", "refresh_token", "access_token_repr", "access_token_json", "refresh_token_json"],
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


def test_configure_logging_sets_split_levels(restore_root_logger: None) -> None:
    configure_logging(app_level="DEBUG", third_party_level="ERROR")
    assert logging.getLogger("spotify_project").level == logging.DEBUG
    # third-party = root level
    assert logging.getLogger().level == logging.ERROR


def test_configure_logging_attaches_redact_filter_to_handler(restore_root_logger: None) -> None:
    """The filter must sit on the handler: logger-level filters never see records propagated from child loggers."""
    configure_logging()
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, TqdmLoggingHandler)]
    assert len(handlers) == 1
    assert any(isinstance(f, RedactAuthFilter) for f in handlers[0].filters)


def test_configure_logging_redacts_propagated_child_logger_records(restore_root_logger: None, capsys: pytest.CaptureFixture[str]) -> None:
    """End-to-end: a credential logged through a third-party child logger reaches the output redacted.

    This is the exact threat model the module docstring claims to defend against — it used to fail when the filter sat on the root logger.
    """
    configure_logging()
    logging.getLogger("spotipy.client").warning("Authorization: Bearer secretTOKEN123")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "secretTOKEN123" not in combined
    assert "***REDACTED***" in combined


def test_configure_logging_rejects_invalid_level(restore_root_logger: None) -> None:
    """An unknown level name raises ValueError (setLevel's native string validation)."""
    with pytest.raises(ValueError, match="Unknown level"):
        configure_logging(app_level="NOT_A_LEVEL")
