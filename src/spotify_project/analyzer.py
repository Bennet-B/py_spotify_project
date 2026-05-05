from __future__ import annotations

# pyright: reportUnknownMemberType=false
# matplotlib stubs use `**kwargs: Unknown` on every Axes method (text, bar,
# barh, set_xlabel, set_ylabel, set_title, invert_yaxis, tight_layout, …).
# The methods themselves are fully typed; only the pass-through kwargs are
# Unknown.  A per-file disable is the narrowest scope available — there is
# no per-call-site workaround for `**kwargs: Unknown` propagation.
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .models import Playlist


class Analyzer(ABC):
    """Abstract analyzer over a track DataFrame.

    Concrete subclasses override ``analyze`` (returns a summary DataFrame)
    and ``plot`` (renders the result onto a Matplotlib Axes provided by
    the caller). Each subclass MUST also declare a non-empty class-level
    ``title``; this is enforced at class-definition time.

    Attributes:
        title: Short title; appears as the plot's title and is used as the
            key in ``PlaylistAnalyzer.run_all``'s result dict, so collisions
            between subclasses would silently overwrite results.
    """

    title: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "title", None):
            raise TypeError(
                f"Analyzer subclass {cls.__name__} must define a non-empty "
                "class attribute 'title'"
            )

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a summary DataFrame derived from the track-level df."""

    @abstractmethod
    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render ``summary`` onto ``ax``. No figure-level mutation."""


class GenreAnalyzer(Analyzer):
    """Top genres by track count, with empty / sparse data handled.

    Args:
        top_n: How many genres to return; default 15.
    """

    title = "Top Genres"

    def __init__(self, top_n: int = 15) -> None:
        self.top_n = top_n

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count genre frequency across all tracks and return the top N.

        Args:
            df: Track-level DataFrame with a ``genres`` column
                (each cell is a list of strings).

        Returns:
            DataFrame with columns ``genre`` and ``count``, sorted
            descending by count, limited to ``top_n`` rows.
        """
        if df.empty:
            return pd.DataFrame({"genre": [], "count": []})
        exploded = df.explode("genres").dropna(subset=["genres"])
        if exploded.empty:
            return pd.DataFrame({"genre": [], "count": []})
        return (
            exploded.groupby("genres", as_index=False)
            .size()
            .rename(columns={"genres": "genre", "size": "count"})
            .sort_values("count", ascending=False)
            .head(self.top_n)
            .reset_index(drop=True)
        )

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a horizontal bar chart of genre counts.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``genre`` and ``count``.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No genre data", ha="center", va="center")
            ax.set_title(self.title)
            return
        ax.barh(summary["genre"], summary["count"])
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        ax.set_title(self.title)


class YearAnalyzer(Analyzer):
    """Release-year distribution, robust to year-only release_date strings.

    Args:
        bucket_size: Year-bucket width. ``1`` (default) yields per-year bars.
            ``5`` groups into 5-year buckets (1970, 1975, 1980, ...); ``10``
            into decades (1970, 1980, ...). The reported ``year`` value is
            always the bucket's lower bound. Must be a positive integer.

    Raises:
        ValueError: If ``bucket_size`` is not a positive integer.
    """

    title = "Release Year Distribution"

    def __init__(self, bucket_size: int = 1) -> None:
        if bucket_size < 1:
            raise ValueError(
                f"bucket_size must be a positive integer, got {bucket_size}"
            )
        self.bucket_size = bucket_size

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tracks per release year (or per year-bucket).

        Handles both full ISO dates (``2020-01-01``) and year-only strings
        (``1979``). Rows with ``None`` or unparseable release_date are dropped.
        When ``bucket_size > 1``, years are floor-divided onto bucket
        boundaries before counting.

        Args:
            df: Track-level DataFrame with a ``release_date`` column.

        Returns:
            DataFrame with columns ``year`` (int — bucket lower bound) and
            ``count``, sorted ascending by year.
        """
        if df.empty or "release_date" not in df.columns:
            return pd.DataFrame({"year": [], "count": []})
        years = (
            pd.to_numeric(df["release_date"].str.slice(0, 4), errors="coerce")
            .dropna()
            .astype(int)
        )
        if years.empty:
            return pd.DataFrame({"year": [], "count": []})
        if self.bucket_size > 1:
            years = (years // self.bucket_size) * self.bucket_size
        return (
            years.value_counts()
            .sort_index()
            .rename_axis("year")
            .reset_index(name="count")
        )

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a vertical bar chart of track counts per year-bucket.

        Bar width is proportional to ``bucket_size`` so adjacent buckets
        touch (decade plot looks like a histogram, not isolated columns).

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``year`` and ``count``.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No year data", ha="center", va="center")
            ax.set_title(self.title)
            return
        ax.bar(
            summary["year"],
            summary["count"],
            width=self.bucket_size * 0.9,
            align="edge" if self.bucket_size > 1 else "center",
        )
        xlabel = (
            "Year"
            if self.bucket_size == 1
            else f"Year ({self.bucket_size}-year buckets)"
        )
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Track count")
        ax.set_title(self.title)


def _zip_pairs(row: pd.Series[Any]) -> list[tuple[str, str]]:
    """Return a list of (artist_id, artist_name) tuples from a track row.

    Used by ArtistAnalyzer to explode parallel list columns in lock-step.

    Args:
        row: A DataFrame row with ``artist_ids`` and ``artist_names`` list
            columns.

    Returns:
        List of ``(id, name)`` tuples, one per artist.
    """
    return list(zip(row["artist_ids"], row["artist_names"], strict=True))


class ArtistAnalyzer(Analyzer):
    """Top artists by track count and total minutes.

    With ``primary_only=False`` (default), every artist on every track gets
    naive credit — a 4-minute track with two artists adds 4 minutes to each.
    With ``primary_only=True``, only the first-listed (lead) artist on each
    track is counted.

    Args:
        top_n: How many artists to return; default 15.
        primary_only: If True, count only each track's primary artist;
            default False (count all listed artists).
    """

    title = "Top Artists"

    def __init__(self, top_n: int = 15, primary_only: bool = False) -> None:
        self.top_n = top_n
        self.primary_only = primary_only

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate track count and total minutes per artist.

        Args:
            df: Track-level DataFrame with either ``artist_ids`` /
                ``artist_names`` (list columns; used when
                ``primary_only=False``) or ``primary_artist_id`` /
                ``primary_artist_name`` (used when ``primary_only=True``).

        Returns:
            DataFrame with columns ``artist_id``, ``artist_name``,
            ``track_count``, ``total_minutes``, sorted descending by
            ``track_count``, limited to ``top_n`` rows. Ties at the
            ``top_n`` cutoff are broken by ``artist_id`` ascending
            (groupby's default ordering).

        Raises:
            ValueError: If ``primary_only=False`` and the per-row ``artist_ids``
                and ``artist_names`` lists are not the same length. This
                surfaces schema corruption — the rows produced by
                ``PlaylistAnalyzer.from_playlist`` are guaranteed to be
                in lock-step.
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
            return empty

        if self.primary_only:
            required = {"primary_artist_id", "primary_artist_name", "duration_min"}
            if not required.issubset(df.columns):
                return empty
            source = df[
                ["primary_artist_id", "primary_artist_name", "duration_min"]
            ].rename(
                columns={
                    "primary_artist_id": "artist_id",
                    "primary_artist_name": "artist_name",
                }
            )
        else:
            required = {"artist_ids", "artist_names", "duration_min"}
            if not required.issubset(df.columns):
                return empty
            # Explode artist_ids and artist_names in lock-step so each
            # exploded row holds the matching name. Pandas explode preserves
            # ordering within the row, so the parallelism is preserved.
            exploded = df[["artist_ids", "artist_names", "duration_min"]].copy()
            exploded["pair"] = exploded.apply(_zip_pairs, axis=1)
            exploded = exploded.explode("pair").dropna(subset=["pair"])
            if exploded.empty:
                return empty
            source = pd.DataFrame(
                {
                    "artist_id": exploded["pair"].map(lambda p: p[0]),
                    "artist_name": exploded["pair"].map(lambda p: p[1]),
                    "duration_min": exploded["duration_min"],
                }
            )

        source = source.dropna(subset=["artist_id"])
        if source.empty:
            return empty
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
        return grouped

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a horizontal bar chart of artists by track count.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; must include ``artist_name``
                and ``track_count`` columns.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No artist data", ha="center", va="center")
            ax.set_title(self.title)
            return
        ax.barh(summary["artist_name"], summary["track_count"])
        ax.invert_yaxis()
        ax.set_xlabel("Track count")
        ax.set_title(self.title)


class PopularityAnalyzer(Analyzer):
    """Distribution of Spotify popularity scores (0-100) across the playlist.

    Args:
        bins: Number of equal-width bins covering [0, 100]; default 10.
            Must be a positive integer.

    Raises:
        ValueError: If ``bins`` is not a positive integer.
    """

    title = "Popularity Distribution"

    def __init__(self, bins: int = 10) -> None:
        if bins < 1:
            raise ValueError(f"bins must be a positive integer, got {bins}")
        self.bins = bins

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bin track popularity into equal-width buckets across [0, 100].

        Args:
            df: Track-level DataFrame with a ``popularity`` column (0-100).

        Returns:
            DataFrame with columns ``bin_low``, ``bin_high``, ``count``.
            The right edge of the last bin is inclusive (np.histogram
            behavior); all other bins are right-open.
        """
        empty = pd.DataFrame({"bin_low": [], "bin_high": [], "count": []})
        if df.empty or "popularity" not in df.columns:
            return empty
        values = pd.to_numeric(df["popularity"], errors="coerce").dropna()
        if values.empty:
            return empty
        counts, edges = np.histogram(values, bins=self.bins, range=(0, 100))
        return pd.DataFrame(
            {
                "bin_low": edges[:-1],
                "bin_high": edges[1:],
                "count": counts,
            }
        )

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a histogram of popularity counts plus a vertical mean line.

        The mean is computed from the bin midpoints weighted by counts —
        accurate enough for visual annotation, even if the underlying data
        spread within bins is lost.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No popularity data", ha="center", va="center")
            ax.set_title(self.title)
            return
        widths = summary["bin_high"] - summary["bin_low"]
        ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge")
        midpoints = (summary["bin_low"] + summary["bin_high"]) / 2
        weighted_mean = (midpoints * summary["count"]).sum() / summary["count"].sum()
        ax.axvline(weighted_mean, linestyle="--", linewidth=1)
        ax.set_xlabel("Popularity (0-100)")
        ax.set_ylabel("Track count")
        ax.set_xlim(0, 100)
        ax.set_title(f"{self.title} (mean ≈ {weighted_mean:.1f})")


class DurationAnalyzer(Analyzer):
    """Track-duration distribution (in minutes) plus playlist total runtime.

    Args:
        bins: Number of equal-width bins; default 20. Range is inferred from
            the data (no fixed [0, 100] like popularity). Must be positive.

    Raises:
        ValueError: If ``bins`` is not a positive integer.
    """

    title = "Track Duration Distribution"

    def __init__(self, bins: int = 20) -> None:
        if bins < 1:
            raise ValueError(f"bins must be a positive integer, got {bins}")
        self.bins = bins

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bin track durations and report exact minutes per bin.

        Args:
            df: Track-level DataFrame with a ``duration_min`` column.

        Returns:
            DataFrame with columns ``bin_low``, ``bin_high``, ``count``,
            ``minutes_in_bin``. ``minutes_in_bin`` is the exact sum of
            durations falling in the bin — useful for total-runtime
            annotation in ``plot``.
        """
        empty = pd.DataFrame(
            {"bin_low": [], "bin_high": [], "count": [], "minutes_in_bin": []}
        )
        if df.empty or "duration_min" not in df.columns:
            return empty
        values = pd.to_numeric(df["duration_min"], errors="coerce").dropna()
        if values.empty:
            return empty
        counts, edges = np.histogram(values, bins=self.bins)
        # Exact minutes per bin: digitize each value to its bin index, then
        # sum durations weighted into bincount. np.digitize uses 1-based
        # indices for values inside the range; subtract 1 and clip the last
        # edge so the rightmost value lands in the final bin (matches
        # np.histogram's right-inclusive last bin).
        bin_idx = np.clip(np.digitize(values, edges) - 1, 0, self.bins - 1)
        minutes_in_bin = np.bincount(bin_idx, weights=values, minlength=self.bins)
        return pd.DataFrame(
            {
                "bin_low": edges[:-1],
                "bin_high": edges[1:],
                "count": counts,
                "minutes_in_bin": minutes_in_bin,
            }
        )

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a duration histogram with total-runtime annotation in the title.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No duration data", ha="center", va="center")
            ax.set_title(self.title)
            return
        widths = summary["bin_high"] - summary["bin_low"]
        ax.bar(summary["bin_low"], summary["count"], width=widths, align="edge")
        total_min = summary["minutes_in_bin"].sum()
        hours = int(total_min // 60)
        minutes = int(total_min % 60)
        ax.set_xlabel("Duration (minutes)")
        ax.set_ylabel("Track count")
        ax.set_title(f"{self.title} (total runtime: {hours}h {minutes}m)")


class PlaylistAnalyzer:
    """Orchestrator: holds a track DataFrame and runs registered Analyzers.

    Attributes:
        df: The track-level DataFrame (one row per track).
        analyzers: Registered Analyzer instances; default is all built-in.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        analyzers: list[Analyzer] | None = None,
    ) -> None:
        self.df = df
        self.analyzers = (
            analyzers
            if analyzers is not None
            else [
                GenreAnalyzer(),
                YearAnalyzer(),
            ]
        )

    @classmethod
    def from_playlist(
        cls,
        playlist: Playlist,
        analyzers: list[Analyzer] | None = None,
    ) -> PlaylistAnalyzer:
        """Build a PlaylistAnalyzer from a Playlist by flattening tracks.

        Each Track's ``primary_artist`` is read for the ``primary_artist_*``
        and ``genres`` columns. Local files (``is_local=True``) yield
        empty genres and ``None`` for artist IDs.

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
            release_year: int | None
            if release_date and release_date[:4].isdigit():
                release_year = int(release_date[:4])
            else:
                release_year = None
            rows.append(
                {
                    "track_id": t.id,
                    "name": t.name,
                    "primary_artist_id": primary.id if primary else None,
                    "primary_artist_name": primary.name if primary else "",
                    "all_artists": " | ".join(a.name for a in t.artists),
                    "artist_ids": [a.id for a in t.artists],
                    "artist_names": [a.name for a in t.artists],
                    "album_name": t.album_name,
                    "release_date": release_date,
                    "release_year": release_year,
                    "duration_ms": t.duration_ms,
                    "duration_min": t.duration_ms / 60_000,
                    "popularity": t.popularity,
                    "explicit": t.explicit,
                    "added_at": t.added_at,
                    "is_local": t.is_local,
                    "genres": list(primary.genres) if primary else [],
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df["release_year"] = df["release_year"].astype("Int64")
        return cls(df=df, analyzers=analyzers)

    def run_all(self) -> dict[str, pd.DataFrame]:
        """Run every registered Analyzer; returns ``{title: summary_df}``."""
        return {a.title: a.analyze(self.df) for a in self.analyzers}

    def plot_all(self, fig: Figure) -> None:
        """Lay out one subplot per analyzer in a vertical stack on ``fig``.

        Reuses the result of ``run_all`` so each analyzer's ``analyze``
        runs exactly once per call (instead of twice if the caller also
        invoked ``run_all`` separately).

        Args:
            fig: Matplotlib Figure to subdivide with subplots.
        """
        n = len(self.analyzers)
        if n == 0:
            return
        summaries = self.run_all()
        axes = fig.subplots(n, 1)
        axes_list = [axes] if n == 1 else list(axes)
        for ax, analyzer in zip(axes_list, self.analyzers, strict=False):
            analyzer.plot(ax, summaries[analyzer.title])
        fig.tight_layout()

    def to_parquet(self, path: Path) -> None:
        """Write the underlying DataFrame to parquet for offline use.

        Args:
            path: Destination file path (must have a .parquet extension
                or be accepted by the parquet engine).
        """
        self.df.to_parquet(path)
