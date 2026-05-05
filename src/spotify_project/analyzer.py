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
    """Release-year distribution, robust to year-only release_date strings."""

    title = "Release Year Distribution"

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Count tracks per release year.

        Handles both full ISO dates (``2020-01-01``) and year-only strings
        (``1979``). Rows with ``None`` or unparseable release_date are dropped.

        Args:
            df: Track-level DataFrame with a ``release_date`` column.

        Returns:
            DataFrame with columns ``year`` (int) and ``count``, sorted
            ascending by year.
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
        return (
            years.value_counts()
            .sort_index()
            .rename_axis("year")
            .reset_index(name="count")
        )

    def plot(self, ax: Axes, summary: pd.DataFrame) -> None:
        """Render a vertical bar chart of track counts per year.

        Args:
            ax: Matplotlib Axes to draw on.
            summary: Output of ``analyze``; columns ``year`` and ``count``.
        """
        if summary.empty:
            ax.text(0.5, 0.5, "No year data", ha="center", va="center")
            ax.set_title(self.title)
            return
        ax.bar(summary["year"], summary["count"])
        ax.set_xlabel("Year")
        ax.set_ylabel("Track count")
        ax.set_title(self.title)


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
