from __future__ import annotations

# pyright: reportUnknownMemberType=false
# matplotlib's Axes stubs forward `**kwargs: Unknown` on most methods; the methods themselves are typed, but the kwarg propagation has no per-call workaround.
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .models import Playlist

logger = logging.getLogger(__name__)

_LOW_COVERAGE_THRESHOLD = 0.7

# A color accepted by Matplotlib: either a CSS hex/name string or an RGB float-triple (0.0–1.0 per channel) as returned by seaborn palettes.
_Color = str | tuple[float, float, float]


def _get_coverage(summary: pd.DataFrame) -> tuple[int, int]:
    """Return the (n_data, n_total) coverage tuple stamped by Analyzer._attach_coverage, or (0, 0) if absent."""
    coverage: tuple[int, int] = summary.attrs.get("coverage", (0, 0))
    return coverage


def _top_n_from_list_column(df: pd.DataFrame, column: str, top_n: int, value_label: str) -> pd.DataFrame:
    """Frequency-count a DataFrame list-column and return the top N.

    Used by TagAnalyzer (column='tags') and GenreAnalyzer (column='genres') —
    both share the explode-and-group-by shape; only the column name and the
    output label differ.

    Args:
        df: Track-level DataFrame.
        column: Name of the list-valued column to count (e.g. 'tags' or 'genres').
        top_n: Number of rows to return.
        value_label: Output column name for the labels (e.g. 'tag' or 'genre').

    Returns:
        DataFrame with columns ``[value_label, 'count']``, descending count,
        limited to ``top_n`` rows. Empty DataFrame with the right columns
        when ``df`` is empty or ``column`` is missing.
    """
    empty = pd.DataFrame({value_label: [], "count": []})
    if df.empty or column not in df.columns:
        return empty
    exploded = df.explode(column).dropna(subset=[column])
    if exploded.empty:
        return empty
    return exploded.groupby(column, as_index=False).size().rename(columns={column: value_label, "size": "count"}).sort_values("count", ascending=False).head(top_n).reset_index(drop=True)


def _style_axes(ax: Axes, base_title: str, summary: pd.DataFrame) -> None:
    """Apply a consistent style and coverage suffix to an Axes.

    Reads ``summary.attrs["coverage"]`` (a ``(n_data, n_total)`` tuple attached by ``Analyzer._attach_coverage``);
    when present and < 100%, appends a coverage suffix to the title.

    Args:
        ax: The Matplotlib Axes to style.
        base_title: The analyzer's effective title, before coverage suffix.
        summary: The analyze() output. Used to read ``attrs["coverage"]``.
    """
    suffix = ""
    match _get_coverage(summary):
        case (n_data, n_total) if n_total > 0 and n_data < n_total:
            pct = n_data / n_total
            suffix = f" ({n_data}/{n_total} tracks, {pct:.0%} coverage)"
        case _:
            pass
    ax.set_title(base_title + suffix, fontsize=12, fontweight="bold")
    ax.tick_params(colors="#666", labelsize=9)
    xlabel = ax.get_xlabel()
    ylabel = ax.get_ylabel()
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color="#666")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color="#666")


class Analyzer(ABC):
    """Abstract analyzer over a track DataFrame.

    Concrete subclasses override ``analyze`` (returns a summary DataFrame) and
    ``plot`` (renders the result onto a Matplotlib Axes provided by the caller).
    Each subclass MUST also declare a non-empty class-level ``title``; this is
    enforced at class-definition time.

    Attributes:
        title: Short title; appears as the plot's title and is used as the
            key in ``PlaylistAnalyzer.run_all``'s result dict.
        default_color: Default bar/line color for plot().
        skip_message: If set, ``PlaylistAnalyzer.run_all`` and ``plot_all``
            skip this analyzer when its ``coverage()`` returns ``(0, n)``.
            Default None means "always run, even at zero coverage" (the
            analyzer's own ``plot`` renders an empty-state placeholder).
            Use skip_message for analyzers whose data source can be entirely
            absent (e.g. tags without a Last.fm key) — the user-visible
            message is logged when the skip triggers.
    """

    title: ClassVar[str]
    default_color: ClassVar[_Color] = "#1f77b4"
    skip_message: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "title", None):
            raise TypeError(f"Analyzer subclass {cls.__name__} must define a non-empty class attribute 'title'")

    @property
    def effective_title(self) -> str:
        """Return the per-instance title if set, else the class-level ``title``.

        Per-instance titles are set by passing ``title=`` to a concrete analyzer's constructor.
        They let multiple instances of the same subclass coexist in one ``PlaylistAnalyzer`` without colliding on the dict key in ``run_all``.
        """
        instance_title = getattr(self, "_instance_title", None)
        return instance_title if instance_title is not None else type(self).title

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a summary DataFrame derived from the track-level df."""

    @abstractmethod
    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render ``summary`` onto ``ax``. No figure-level mutation."""

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Return ``(n_with_usable_data, n_total)`` for this analyzer.

        Default returns full coverage. Override in subclasses where data can plausibly be missing (e.g. ``release_date`` for some albums, ``genres`` for some artists).

        Args:
            df: The track-level DataFrame.

        Returns:
            ``(n_with_usable_data, n_total)``.
        """
        n = len(df)
        return (n, n)

    def _attach_coverage(self, summary: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
        """Stamp coverage onto ``summary.attrs["coverage"]``, warn when low, and return.

        Args:
            summary: The DataFrame that ``analyze`` is about to return.
            df: The track-level DataFrame the analyzer worked from.

        Returns:
            ``summary``, with ``attrs["coverage"]`` set.

        Side effects:
            Emits ``logger.warning`` when ``n_data / n_total < _LOW_COVERAGE_THRESHOLD`` (0.7).
        """
        n_data, n_total = self.coverage(df)
        if n_total > 0 and n_data / n_total < _LOW_COVERAGE_THRESHOLD:
            logger.warning("%s: low coverage %d/%d (%.0f%%)", self.effective_title, n_data, n_total, 100 * n_data / n_total)
        summary.attrs["coverage"] = (n_data, n_total)
        return summary


class TagAnalyzer(Analyzer):
    """Top Last.fm tags by track count.

    Tags are raw folksonomy: real genres alongside eras (``00s``), geography
    (``british``), behavior (``seen live``), sentiment (``favorite``). Useful
    as a complete view of how listeners describe these artists, and as a
    curation aid when refining the whitelist that drives GenreAnalyzer.

    Skipped by ``PlaylistAnalyzer.run_all`` when no track has any tag — typically
    because LASTFM_API_KEY is unset.

    Args:
        top_n: How many tags to return; default 15.
        title: Optional per-instance title override.
    """

    title = "Top Tags"
    skip_message = "no tag data — set LASTFM_API_KEY to enable."

    def __init__(self, top_n: int = 15, *, title: str | None = None) -> None:
        self.top_n = top_n
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows whose ``tags`` list is non-empty."""
        if df.empty or "tags" not in df.columns:
            return (0, len(df))
        n_with = int(df["tags"].apply(lambda t: bool(t) if isinstance(t, list) else False).sum())  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tag frequency across all tracks and return the top N.

        Args:
            df: Track-level DataFrame with a ``tags`` column (list-valued).

        Returns:
            DataFrame with columns ``tag`` and ``count``, descending count,
            limited to ``top_n`` rows.
        """
        result = _top_n_from_list_column(df, "tags", self.top_n, "tag")
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a horizontal bar chart of tag counts.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``tag`` and ``count``.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No tag data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        ax.barh(summary["tag"], summary["count"], color=c)
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        _style_axes(ax, self.effective_title, summary)


class GenreAnalyzer(Analyzer):
    """Top genres by track count, with empty / sparse data handled.

    Args:
        top_n: How many genres to return; default 15.
    """

    title = "Top Genres"
    skip_message = "no genres after whitelist filtering — set LASTFM_API_KEY to enable, or extend GENRE_WHITELIST in genre_taxonomy.py."

    def __init__(self, top_n: int = 15, *, title: str | None = None) -> None:
        self.top_n = top_n
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows whose ``genres`` list is non-empty."""
        if df.empty or "genres" not in df.columns:
            return (0, len(df))
        n_with = int(df["genres"].apply(lambda g: bool(g) if isinstance(g, list) else False).sum())  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count genre frequency across all tracks and return the top N.

        Args:
            df: Track-level DataFrame with a ``genres`` column (list-valued).

        Returns:
            DataFrame with columns ``genre`` and ``count``, descending count,
            limited to ``top_n`` rows.
        """
        result = _top_n_from_list_column(df, "genres", self.top_n, "genre")
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a horizontal bar chart of genre counts, plus a missing-fraction band beneath the bars when coverage is partial.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``genre`` and ``count``.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No genre data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        ax.barh(summary["genre"], summary["count"], color=c)
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        match _get_coverage(summary):
            case (n_data, n_total) if n_total > 0 and n_data < n_total:
                missing_frac = 1 - n_data / n_total
                # Draw a thin grey band just below the axes, with width proportional to the missing fraction.
                # transAxes puts both x and y in axes fraction (0..1, with negative values meaning below-bottom); clip_on=False lets it render outside the axes box.
                ax.axhspan(
                    ymin=-0.05,
                    ymax=-0.01,
                    xmin=0.0,
                    xmax=missing_frac,
                    facecolor="#999",
                    alpha=0.6,
                    transform=ax.transAxes,
                    clip_on=False,
                )
            case _:
                pass
        _style_axes(ax, self.effective_title, summary)


class YearAnalyzer(Analyzer):
    """Release-year distribution, robust to year-only release_date strings.

    Args:
        bucket_size: Year-bucket width. ``1`` (default) yields per-year bars.
            ``5`` groups into 5-year buckets (1970, 1975, 1980, ...); ``10`` into decades (1970, 1980, ...).
            The reported ``year`` value is always the bucket's lower bound. Must be a positive integer.

    Raises:
        ValueError: If ``bucket_size`` is not a positive integer.
    """

    title = "Release Year Distribution"

    def __init__(self, bucket_size: int = 1, *, title: str | None = None) -> None:
        if bucket_size < 1:
            raise ValueError(f"bucket_size must be a positive integer, got {bucket_size}")
        self.bucket_size = bucket_size
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows with a parseable 4-digit release year."""
        if df.empty or "release_date" not in df.columns:
            return (0, len(df))
        parsed = pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce")
        n_with = int(parsed.notna().sum())
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tracks per release year (or per year-bucket).

        Handles both full ISO dates (``2020-01-01``) and year-only strings (``1979``). Rows with ``None`` or unparseable release_date are dropped.
        When ``bucket_size > 1``, years are floor-divided onto bucket boundaries before counting.

        Args:
            df: Track-level DataFrame with a ``release_date`` column.

        Returns:
            DataFrame with columns ``year`` (int — bucket lower bound) and ``count``, sorted ascending by year.
        """
        if df.empty or "release_date" not in df.columns:
            return self._attach_coverage(pd.DataFrame({"year": [], "count": []}), df)
        years = pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce").dropna().astype(int)
        if years.empty:
            return self._attach_coverage(pd.DataFrame({"year": [], "count": []}), df)
        if self.bucket_size > 1:
            years = (years // self.bucket_size) * self.bucket_size
        result = years.value_counts().sort_index().rename_axis("year").reset_index(name="count")
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a vertical bar chart of track counts per year-bucket.

        Bar width is proportional to ``bucket_size`` so adjacent buckets touch (decade plot looks like a histogram, not isolated columns).

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``year`` and ``count``.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No year data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        ax.bar(
            summary["year"],
            summary["count"],
            width=self.bucket_size * 0.9,
            align="edge" if self.bucket_size > 1 else "center",
            color=c,
        )
        xlabel = "Year" if self.bucket_size == 1 else f"Year ({self.bucket_size}-year buckets)"
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Track count")
        _style_axes(ax, self.effective_title, summary)


class ArtistAnalyzer(Analyzer):
    """Top artists by track count and total minutes.

    With ``primary_only=False`` (default), every artist on every track gets naive credit — a 4-minute track with two artists adds 4 minutes to each.
    With ``primary_only=True``, only the first-listed (lead) artist on each track is counted.
    Coverage counts rows with a non-null ``primary_artist_id``; local files and tracks whose artists were dropped during enrichment lower it.

    Args:
        top_n: How many artists to return; default 15.
        primary_only: If True, count only each track's primary artist; default False (count all listed artists).
    """

    title = "Top Artists"

    def __init__(self, top_n: int = 15, primary_only: bool = False, *, title: str | None = None) -> None:
        self.top_n = top_n
        self.primary_only = primary_only
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows with a non-null ``primary_artist_id`` (local files and tracks dropped during artist enrichment have ``None``)."""
        if df.empty or "primary_artist_id" not in df.columns:
            return (0, len(df))
        n_with = int(df["primary_artist_id"].notna().sum())
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate track count and total minutes per artist.

        Args:
            df: Track-level DataFrame with either ``artist_ids``/``artist_names`` (list columns; used when ``primary_only=False``) or ``primary_artist_id``/``primary_artist_name`` (used when ``primary_only=True``).

        Returns:
            DataFrame with columns ``artist_id``, ``artist_name``, ``track_count``, ``total_minutes``, sorted descending by ``track_count``, limited to ``top_n`` rows.
            Ties at the ``top_n`` cutoff are broken by ``artist_id`` ascending (groupby's default ordering).

        Raises:
            ValueError: If ``primary_only=False`` and the per-row ``artist_ids`` and ``artist_names`` lists are not the same length.
                This surfaces schema corruption — the rows produced by ``PlaylistAnalyzer.from_playlist`` are guaranteed to be in lock-step.
        """
        empty = pd.DataFrame(
            {
                "artist_id": [],
                "artist_name": [],
                "track_count": [],
                "total_minutes": [],
            }
        )
        if df.empty:
            return self._attach_coverage(empty, df)

        if self.primary_only:
            required = {"primary_artist_id", "primary_artist_name", "duration_min"}
            if not required.issubset(df.columns):
                return self._attach_coverage(empty, df)
            source = df[["primary_artist_id", "primary_artist_name", "duration_min"]].rename(
                columns={
                    "primary_artist_id": "artist_id",
                    "primary_artist_name": "artist_name",
                }
            )
        else:
            required = {"artist_ids", "artist_names", "duration_min"}
            if not required.issubset(df.columns):
                return self._attach_coverage(empty, df)
            # Zip into pairs before explode: keeps each id with its matching name even though pandas explode preserves order.
            exploded = df[["artist_ids", "artist_names", "duration_min"]].copy()
            exploded["pair"] = exploded.apply(lambda row: list(zip(row["artist_ids"], row["artist_names"], strict=True)), axis=1)  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
            exploded = exploded.explode("pair").dropna(subset=["pair"])
            if exploded.empty:
                return self._attach_coverage(empty, df)
            source = pd.DataFrame(
                {
                    "artist_id": exploded["pair"].map(lambda p: p[0]),
                    "artist_name": exploded["pair"].map(lambda p: p[1]),
                    "duration_min": exploded["duration_min"],
                }
            )

        source = source.dropna(subset=["artist_id"])
        if source.empty:
            return self._attach_coverage(empty, df)
        grouped = (
            source.groupby(["artist_id", "artist_name"], as_index=False)
            .agg(
                track_count=("duration_min", "size"),
                total_minutes=("duration_min", "sum"),
            )
            .sort_values("track_count", ascending=False)
            .head(self.top_n)
            .reset_index(drop=True)
        )
        return self._attach_coverage(grouped, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a horizontal bar chart of artists by track count.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; must include ``artist_name`` and ``track_count`` columns.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No artist data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        ax.barh(summary["artist_name"], summary["track_count"], color=c)
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        _style_axes(ax, self.effective_title, summary)


class DurationAnalyzer(Analyzer):
    """Track-duration distribution (in minutes) plus playlist total runtime.

    Args:
        bins: Number of equal-width bins; default 20. Range is inferred from the data. Must be positive.

    Raises:
        ValueError: If ``bins`` is not a positive integer.
    """

    title = "Track Duration Distribution"

    def __init__(self, bins: int = 20, *, title: str | None = None) -> None:
        if bins < 1:
            raise ValueError(f"bins must be a positive integer, got {bins}")
        self.bins = bins
        self._instance_title = title

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bin track durations and report exact minutes per bin.

        Args:
            df: Track-level DataFrame with a ``duration_min`` column.

        Returns:
            DataFrame with columns ``bin_low``, ``bin_high``, ``count``, ``minutes_in_bin``.
            ``minutes_in_bin`` is the exact sum of durations falling in the bin — useful for total-runtime annotation in ``plot``.
        """
        empty = pd.DataFrame({"bin_low": [], "bin_high": [], "count": [], "minutes_in_bin": []})
        if df.empty or "duration_min" not in df.columns:
            return self._attach_coverage(empty, df)
        values = pd.to_numeric(df["duration_min"], errors="coerce").dropna()
        if values.empty:
            return self._attach_coverage(empty, df)
        counts, edges = np.histogram(values, bins=self.bins)
        # Exact minutes per bin: digitize each value to its bin index, then sum durations weighted into bincount.
        # np.digitize uses 1-based indices for values inside the range;
        # subtract 1 and clip the last edge so the rightmost value lands in the final bin (matches np.histogram's right-inclusive last bin).
        bin_idx = np.clip(np.digitize(values, edges) - 1, 0, self.bins - 1)
        minutes_in_bin = np.bincount(bin_idx, weights=values, minlength=self.bins)
        result = pd.DataFrame(
            {
                "bin_low": edges[:-1],
                "bin_high": edges[1:],
                "count": counts,
                "minutes_in_bin": minutes_in_bin,
            }
        )
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render a duration histogram with total-runtime annotation in the title.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``.
            color: Bar color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No duration data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        widths = summary["bin_high"] - summary["bin_low"]
        ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge", color=c)
        total_min = round(summary["minutes_in_bin"].sum())
        hours = total_min // 60
        minutes = total_min % 60
        ax.set_xlabel("Duration (minutes)")
        ax.set_ylabel("Track count")
        _style_axes(ax, f"{self.effective_title} (total runtime: {hours}h {minutes}m)", summary)


class TimelineAnalyzer(Analyzer):
    """Track-addition timeline grouped by period, based on ``added_at`` timestamps.

    Rows with missing or unparseable ``added_at`` are dropped. Coverage reflects the
    fraction of tracks that have a valid ``added_at`` value.

    Args:
        freq: pandas Period frequency string. Default ``"M"`` (month). ``"Y"`` for yearly, ``"W"`` for weekly. Validated by pandas.
    """

    title = "Track Timeline"

    def __init__(self, freq: str = "M", *, title: str | None = None) -> None:
        self.freq = freq
        self._instance_title = title

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        """Count rows with a valid ``added_at`` timestamp."""
        if df.empty or "added_at" not in df.columns:
            return (0, len(df))
        n_with = int(pd.to_datetime(df["added_at"], errors="coerce", utc=True).notna().sum())
        return (n_with, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Group track additions into time-period buckets.

        Only ``added_at`` is used; rows with a missing or unparseable value are dropped.

        Args:
            df: Track-level DataFrame; must contain ``added_at``.

        Returns:
            DataFrame with columns ``period`` (pandas Period) and ``count``, sorted ascending by period.
        """
        empty = pd.DataFrame({"period": [], "count": []})
        if df.empty:
            return self._attach_coverage(empty, df)

        raw: pd.Series[Any] = df["added_at"] if "added_at" in df.columns else pd.Series([], dtype=object)
        values: pd.Series[Any] = pd.to_datetime(raw, errors="coerce", utc=True).dropna()
        if values.empty:
            return self._attach_coverage(empty, df)
        # Strip timezone before to_period — pandas warns otherwise, and the period (month / year / week) is coarse enough that tz is irrelevant.
        periods: pd.Series[Any] = values.dt.tz_localize(None).dt.to_period(self.freq)
        result: pd.DataFrame = periods.value_counts().sort_index().rename_axis("period").reset_index(name="count")
        return self._attach_coverage(result, df)

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: _Color | None = None) -> None:
        """Render an area-style line chart of track additions over time.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``period`` and ``count``.
            color: Line/fill color; defaults to the class's ``default_color``.
        """
        c = color if color is not None else self.default_color
        if summary.empty:
            ax.text(0.5, 0.5, "No timeline data", ha="center", va="center")
            _style_axes(ax, self.effective_title, summary)
            return
        x: pd.Series[Any] = summary["period"].apply(lambda p: p.start_time)  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
        ax.fill_between(x, summary["count"], step="mid", alpha=0.4, color=c)
        ax.plot(x, summary["count"], marker="o", color=c)
        ax.set_xlabel("Time")
        ax.set_ylabel("Tracks added")
        _style_axes(ax, self.effective_title, summary)


class PlaylistAnalyzer:
    """Orchestrator: holds a track DataFrame and runs registered Analyzers.

    Attributes:
        df: The track-level DataFrame (one row per track).
        analyzers: Registered Analyzer instances; default is all built-in.
    """

    def __init__(self, df: pd.DataFrame, analyzers: list[Analyzer] | None = None) -> None:
        self.df = df
        self.analyzers = (
            analyzers
            if analyzers is not None
            else [
                GenreAnalyzer(),
                TagAnalyzer(),
                YearAnalyzer(),
                ArtistAnalyzer(),
                DurationAnalyzer(),
                TimelineAnalyzer(),
            ]
        )
        # Reject duplicate titles loudly: run_all keys results by title and plot_all renders one subplot per analyzer,
        # so a duplicate would silently render the second analyzer's data under both subplots without raising. Better to fail at construction.
        titles = [a.effective_title for a in self.analyzers]
        if len(set(titles)) != len(titles):
            duplicates = sorted({t for t in titles if titles.count(t) > 1})
            raise ValueError(f"Analyzer titles must be unique; got duplicates: {duplicates}")

    @classmethod
    def from_playlist(cls, playlist: Playlist, analyzers: list[Analyzer] | None = None) -> PlaylistAnalyzer:
        """Build a PlaylistAnalyzer from a Playlist by flattening tracks.

        Each Track's ``primary_artist`` is read for the ``primary_artist_*``, ``tags``, and ``genres`` columns.
        Local files (``is_local=True``) yield empty genres and ``None`` for artist IDs.

        Args:
            playlist: Source Playlist with full Track + Artist data.
            analyzers: Optional Analyzer list; defaults to the built-in set.

        Returns:
            Ready-to-use PlaylistAnalyzer.
        """
        rows: list[dict[str, Any]] = []
        for t in playlist.tracks:
            primary = t.primary_artist
            release_date = t.release_date
            release_year: int | None = int(release_date[:4]) if release_date and release_date[:4].isdigit() else None
            rows.append(
                {
                    "track_id": t.id,
                    "name": t.name,
                    "primary_artist_id": primary.id if primary else None,
                    "primary_artist_name": primary.name if primary else "",
                    "artist_ids": [a.id for a in t.artists],
                    "artist_names": [a.name for a in t.artists],
                    "album_name": t.album_name,
                    "release_date": release_date,
                    "release_year": release_year,
                    "duration_ms": t.duration_ms,
                    "duration_min": t.duration_ms / 60_000,
                    "explicit": t.explicit,
                    "added_at": t.added_at,
                    "is_local": t.is_local,
                    "tags": list(primary.tags) if primary else [],
                    "genres": list(primary.genres) if primary else [],
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df["release_year"] = df["release_year"].astype("Int64")
        return cls(df=df, analyzers=analyzers)

    def run_all(self) -> dict[str, pd.DataFrame]:
        """Run every registered Analyzer; returns ``{title: summary_df}``.

        Analyzers whose ``coverage(df)`` returns ``(0, n)`` AND that have set
        ``skip_message`` are skipped entirely (no entry in the result dict);
        a single INFO log line records the skip and the analyzer's hint.
        """
        out: dict[str, pd.DataFrame] = {}
        for a in self.analyzers:
            if a.skip_message is not None:
                n_data, _ = a.coverage(self.df)
                if n_data == 0:
                    logger.info("Skipping %s: %s", a.effective_title, a.skip_message)
                    continue
            out[a.effective_title] = a.analyze(self.df)
        return out

    def plot_all(self, fig: Figure) -> None:
        """Lay out one subplot per non-skipped analyzer in a vertical stack on ``fig``.

        Analyzers whose ``coverage(df)`` returns ``(0, n)`` AND that have set
        ``skip_message`` are skipped — no subplot allocated. The log line is
        emitted by ``run_all``, which this method calls.

        Args:
            fig: Matplotlib Figure to subdivide with subplots.
        """
        summaries = self.run_all()
        active = [a for a in self.analyzers if a.effective_title in summaries]
        n = len(active)
        if n == 0:
            return
        axes = fig.subplots(n, 1)
        axes_list = [axes] if n == 1 else list(axes)
        palette = sns.color_palette("colorblind", n_colors=n)
        for ax, analyzer, color in zip(axes_list, active, palette, strict=True):
            analyzer.plot(ax, summaries[analyzer.effective_title], color=color)
        fig.tight_layout()

    def to_parquet(self, path: Path) -> None:
        """Write the underlying DataFrame to parquet for offline use.

        Args:
            path: Destination file path (must have a .parquet extension or be accepted by the parquet engine).
        """
        self.df.to_parquet(path)
