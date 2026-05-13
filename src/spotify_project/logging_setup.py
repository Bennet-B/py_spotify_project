"""Logging configuration for the spotify_project package.

Three responsibilities:

1. ``RedactAuthFilter`` — a logging filter that scrubs Bearer / Basic auth headers and refresh tokens from any log record.
   Defense-in-depth: even if a third-party logger (spotipy, urllib3) is bumped to DEBUG, no credentials reach stdout / stderr / committed notebook outputs.

2. ``TqdmLoggingHandler`` — a logging handler that emits records via ``tqdm.write()`` instead of plain stderr.
   Without it, log records emitted during a tqdm progress bar get printed on the same line as the bar, leaving a visual mess.

3. ``configure_logging`` — wires up a split-level scheme: our own code (``spotify_project.*``) at one level, third-party loggers at another.

Notebooks and entry points call ``configure_logging`` once near startup.
Library code never configures logging itself — that decision belongs to the caller.
"""

from __future__ import annotations

import logging
import re

from tqdm import tqdm

__all__ = ["RedactAuthFilter", "TqdmLoggingHandler", "configure_logging"]


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


class TqdmLoggingHandler(logging.Handler):
    """Logging handler that emits records through ``tqdm.write()``.

    ``tqdm`` redraws its progress bar on every update, so anything else written to ``sys.stderr`` (the default for ``StreamHandler``) lands on the same line as the bar and the bar then prints again below.
    ``tqdm.write()`` clears the bar, prints the message on its own line, then redraws the bar — keeping bar and log output legible.
    Falls back transparently to plain stderr when no bar is active.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Format ``record`` and route it through ``tqdm.write``."""
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:  # noqa: BLE001 — stdlib's logging contract: handlers must not raise.
            self.handleError(record)


def configure_logging(app_level: str = "INFO", third_party_level: str = "WARNING") -> None:
    """Configure split-level logging for notebooks / entry points.

    Installs a single ``TqdmLoggingHandler`` on the root logger so log output co-exists cleanly with tqdm progress bars.
    Removes any previously attached handlers so this is safe to call after another library (or a previous notebook cell) has already configured the root logger.
    Attaches ``RedactAuthFilter`` to the root logger.

    Args:
        app_level: Level for ``spotify_project.*`` loggers — our own code. Default ``"INFO"``.
        third_party_level: Level for everything else (spotipy, urllib3, ...). Default ``"WARNING"``.

    Raises:
        AttributeError: If ``app_level`` or ``third_party_level`` is not a valid ``logging`` level name.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = TqdmLoggingHandler()
    handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, third_party_level))
    logging.getLogger("spotify_project").setLevel(getattr(logging, app_level))
    root.addFilter(RedactAuthFilter())
