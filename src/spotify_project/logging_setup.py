"""Logging configuration for the spotify_project package.

Two responsibilities:

1. ``RedactAuthFilter`` — a logging filter that scrubs Bearer / Basic auth headers and refresh tokens from any log record.
   Defense-in-depth: even if a third-party logger (spotipy, urllib3) is bumped to DEBUG, no credentials reach stdout / stderr / committed notebook outputs.

2. ``configure_logging`` — wires up a split-level scheme: our own code (``spotify_project.*``) at one level, third-party loggers at another.

Notebooks and entry points call ``configure_logging`` once near startup.
Library code never configures logging itself — that decision belongs to the caller.
"""

from __future__ import annotations

import logging
import re

__all__ = ["RedactAuthFilter", "configure_logging"]


class RedactAuthFilter(logging.Filter):
    """Scrub Bearer / Basic auth headers and refresh tokens from log records.

    The scrub is in-place on the formatted message.
    The original ``record.msg`` and ``record.args`` are replaced so the redaction survives any later formatter or handler.

    Example:
        >>> import logging
        >>> logger = logging.getLogger("test")
        >>> logger.addFilter(RedactAuthFilter())
        >>> # A record with "Bearer abc123" becomes "***REDACTED***" in output.
    """

    _PATTERN = re.compile(
        r"Bearer\s+[A-Za-z0-9_\-]+"
        r"|Basic\s+[A-Za-z0-9+/=]+"
        r"|'refresh_token':\s*'[^']+'"
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact credential patterns in-place; always return True (keep record)."""
        msg = record.getMessage()
        if "Bearer " in msg or "Basic " in msg or "refresh_token" in msg:
            record.msg = self._PATTERN.sub("***REDACTED***", msg)
            record.args = ()
        return True


def configure_logging(app_level: str = "INFO", third_party_level: str = "WARNING") -> None:
    """Configure split-level logging for notebooks / entry points.

    Calls ``logging.basicConfig`` with ``force=True`` so this is safe to call after another library has already configured the root logger,
    (notebooks re-running setup cells, pytest fixtures, etc.). Attaches ``RedactAuthFilter`` to the root logger.

    Args:
        app_level: Level for ``spotify_project.*`` loggers — our own code. Default ``"INFO"``.
        third_party_level: Level for everything else (spotipy, urllib3, ...). Default ``"WARNING"``.

    Raises:
        AttributeError: If ``app_level`` or ``third_party_level`` is not a valid ``logging`` level name.
    """
    logging.basicConfig(
        level=getattr(logging, third_party_level),
        format="%(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    logging.getLogger("spotify_project").setLevel(getattr(logging, app_level))
    logging.getLogger().addFilter(RedactAuthFilter())
