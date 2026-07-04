"""Pure, reusable computations behind the notebook's exploratory visualizations.

Every function takes the flattened track DataFrame produced by ``PlaylistAnalyzer.from_playlist`` (or a parquet reload of it) and returns a small,
plot-ready DataFrame. No plotting happens here — rendering (seaborn / plotly / networkx) lives in the notebook, keeping these transformations
strictly typed and unit-testable while the visual layer stays free to iterate.

Functions are container-type agnostic where they touch the list columns (``artist_ids``, ``artist_names``, ``genres``): a parquet round-trip
materializes those as numpy arrays, and everything here iterates them generically.
"""

from __future__ import annotations

import calendar
import itertools
import logging
from collections import Counter
from collections.abc import Sequence
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "additions_over_time",
    "artist_first_seen",
    "artist_track_counts",
    "collaboration_edges",
    "discovery_waves",
    "genre_cooccurrence",
    "genre_share_over_time",
    "label_frequencies",
    "release_vs_added",
    "seasonal_profile",
    "year_counts",
]


def _added_periods(df: pd.DataFrame, freq: str) -> pd.Series[Any]:
    """Parse ``added_at`` to timezone-naive pandas Periods, dropping unparseable rows.

    Args:
        df: Track-level DataFrame with an ``added_at`` column.
        freq: pandas Period frequency string (``"M"``, ``"Q"``, ``"W"``, ...).

    Returns:
        Series of Periods aligned to the surviving row index.
    """
    ts = pd.to_datetime(df["added_at"], errors="coerce", utc=True).dropna()
    return ts.dt.tz_localize(None).dt.to_period(freq)


def additions_over_time(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Track additions per period plus cumulative growth in tracks and listening hours.

    Periods with zero additions are included (added=0), so cumulative curves render as proper steps instead of skipping quiet months.

    Args:
        df: Track-level DataFrame with ``added_at`` and ``duration_min`` columns.
        freq: pandas Period frequency string; default monthly.

    Returns:
        DataFrame with columns ``period`` (Timestamp, period start), ``added``, ``cumulative_tracks``, ``cumulative_hours``, sorted ascending.
        Empty (with the right columns) when no row has a usable ``added_at``.
    """
    empty = pd.DataFrame({"period": [], "added": [], "cumulative_tracks": [], "cumulative_hours": []})
    if df.empty or "added_at" not in df.columns:
        return empty
    periods = _added_periods(df, freq)
    if periods.empty:
        return empty
    full_range = pd.period_range(periods.min(), periods.max(), freq=freq)
    added = periods.value_counts().reindex(full_range, fill_value=0).sort_index()
    hours = (df.loc[periods.index, "duration_min"].groupby(periods).sum() / 60.0).reindex(full_range, fill_value=0.0).sort_index()
    return pd.DataFrame(
        {
            "period": full_range.to_timestamp(),
            "added": added.to_numpy(),
            "cumulative_tracks": added.cumsum().to_numpy(),
            "cumulative_hours": hours.cumsum().to_numpy(),
        }
    )


def artist_first_seen(df: pd.DataFrame) -> pd.DataFrame:
    """First time each artist entered the playlist, across all credited artists per track.

    Args:
        df: Track-level DataFrame with ``artist_ids``, ``artist_names`` (parallel list columns), and ``added_at``.

    Returns:
        DataFrame with columns ``artist_id``, ``artist_name``, ``first_added`` (earliest ``added_at`` among the artist's tracks), unsorted.
        Empty (with the right columns) when no row has a usable ``added_at``.
    """
    empty = pd.DataFrame({"artist_id": [], "artist_name": [], "first_added": []})
    required = {"artist_ids", "artist_names", "added_at"}
    if df.empty or not required.issubset(df.columns):
        return empty
    valid = df.dropna(subset=["added_at"])
    if valid.empty:
        return empty
    rows: list[tuple[str, str, Any]] = []
    for ids, names, added_at in zip(valid["artist_ids"], valid["artist_names"], valid["added_at"], strict=True):
        rows.extend((artist_id, artist_name, added_at) for artist_id, artist_name in zip(ids, names, strict=True))
    exploded = pd.DataFrame(rows, columns=["artist_id", "artist_name", "first_added"])
    if exploded.empty:
        return empty
    return exploded.groupby(["artist_id", "artist_name"], as_index=False).agg(first_added=("first_added", "min"))


def discovery_waves(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """New-artist discoveries per period: how many artists appear in the playlist for the first time.

    Args:
        df: Track-level DataFrame (see ``artist_first_seen`` for required columns).
        freq: pandas Period frequency string; default monthly.

    Returns:
        DataFrame with columns ``period`` (Timestamp, period start) and ``new_artists``, gap-free and sorted ascending.
        Empty (with the right columns) when no artist has a usable first-added date.
    """
    empty = pd.DataFrame({"period": [], "new_artists": []})
    first = artist_first_seen(df)
    if first.empty:
        return empty
    periods = _added_periods(first.rename(columns={"first_added": "added_at"}), freq)
    full_range = pd.period_range(periods.min(), periods.max(), freq=freq)
    counts = periods.value_counts().reindex(full_range, fill_value=0).sort_index()
    return pd.DataFrame({"period": full_range.to_timestamp(), "new_artists": counts.to_numpy()})


def seasonal_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Track additions by calendar month (1-12), aggregated across all years.

    Args:
        df: Track-level DataFrame with an ``added_at`` column.

    Returns:
        DataFrame with exactly 12 rows and columns ``month`` (1-12), ``month_name`` (``Jan``..``Dec``), ``added`` (0 for quiet months).
    """
    counts: pd.Series[int] = pd.Series(0, index=pd.RangeIndex(1, 13))
    if not df.empty and "added_at" in df.columns:
        ts = pd.to_datetime(df["added_at"], errors="coerce", utc=True).dropna()
        if not ts.empty:
            counts = ts.dt.month.value_counts().reindex(counts.index, fill_value=0).sort_index()
    return pd.DataFrame(
        {
            "month": range(1, 13),
            "month_name": [calendar.month_abbr[m] for m in range(1, 13)],
            "added": counts.to_numpy(),
        }
    )


def label_frequencies(df: pd.DataFrame, *, field: str = "genres", top_n: int = 30) -> pd.DataFrame:
    """Frequency of the list-valued labels (genres or raw tags) across tracks — the rule-helper bar chart behind "click a genre → tag rule".

    Args:
        df: Track-level DataFrame with the list-valued ``field`` column.
        field: Which label column to count — ``"genres"`` (whitelist-filtered) or ``"tags"`` (raw Last.fm).
        top_n: Number of labels to keep, most frequent first.

    Returns:
        DataFrame with columns ``label``, ``count``, descending count. Empty (with the right columns) when the column is missing or all-empty.
    """
    empty = pd.DataFrame({"label": [], "count": []})
    if df.empty or field not in df.columns:
        return empty
    counts: Counter[str] = Counter(str(label) for cell in df[field] for label in cell)  # pyright: ignore[reportUnknownVariableType] — cell holds a list/ndarray of str
    rows = counts.most_common(top_n)
    if not rows:
        return empty
    return pd.DataFrame(rows, columns=["label", "count"])


def year_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Tracks per release year, pre-binned server-side so a chart click maps to an exact year.

    Args:
        df: Track-level DataFrame with a nullable ``release_year`` column.

    Returns:
        DataFrame with columns ``year`` (int), ``count``, ascending year. Empty (with the right columns) when no track has a usable year.
    """
    empty = pd.DataFrame({"year": [], "count": []})
    if df.empty or "release_year" not in df.columns:
        return empty
    years = df["release_year"].dropna().astype(int)
    if years.empty:
        return empty
    counts = years.value_counts().sort_index()
    return pd.DataFrame({"year": counts.index.to_numpy(), "count": counts.to_numpy()})


def artist_track_counts(df: pd.DataFrame, *, genres: Sequence[str] | None = None, top_n: int = 25) -> pd.DataFrame:
    """Track counts per credited artist, optionally scoped to tracks matching any of the given genres — the cascading "artists within this genre selection" chart.

    All credited artists count, not just the primary one, so a featured artist's presence isn't discarded. Genre matching is case-insensitive.

    Args:
        df: Track-level DataFrame with parallel list columns ``artist_ids`` / ``artist_names`` and (for scoping) ``genres``.
        genres: When non-empty, only tracks whose ``genres`` intersect this set participate.
        top_n: Number of artists to keep, most tracks first.

    Returns:
        DataFrame with columns ``artist_id``, ``artist_name``, ``track_count``, descending count. Empty (with the right columns) when nothing matches.
    """
    empty = pd.DataFrame({"artist_id": [], "artist_name": [], "track_count": []})
    if df.empty or not {"artist_ids", "artist_names"}.issubset(df.columns):
        return empty
    scope = df
    if genres:
        if "genres" not in df.columns:
            return empty
        wanted = {g.lower() for g in genres}
        mask = df["genres"].apply(lambda cell: any(str(g).lower() in wanted for g in cell))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownLambdaType] — cell holds a list/ndarray of str
        scope = df[mask]
    counts: Counter[tuple[str, str]] = Counter()
    for ids, names in zip(scope["artist_ids"], scope["artist_names"], strict=True):
        for artist_id, artist_name in zip(ids, names, strict=True):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType] — cells hold lists/ndarrays of str
            if artist_id is not None:
                counts[(str(artist_id), str(artist_name))] += 1
    rows = [(artist_id, artist_name, count) for (artist_id, artist_name), count in counts.most_common(top_n)]
    if not rows:
        return empty
    return pd.DataFrame(rows, columns=["artist_id", "artist_name", "track_count"])


def genre_share_over_time(df: pd.DataFrame, top_n: int = 8, freq: str = "Q") -> pd.DataFrame:
    """Share of each top genre among genre-tagged additions per period — the raw material for a stacked-area "genre evolution" plot.

    Only rows with both a usable ``added_at`` and at least one genre participate; per-period shares sum to 1.0.
    Genres outside the top ``top_n`` (by overall track count) are folded into an ``other`` column so the palette stays readable.

    Args:
        df: Track-level DataFrame with ``added_at`` and the list-valued ``genres`` column.
        top_n: Number of individually-tracked genres; the rest aggregate into ``other``.
        freq: pandas Period frequency string; default quarterly.

    Returns:
        Wide DataFrame indexed by period start (Timestamp); columns are the top genres (descending overall count) plus ``other`` when applicable.
        Empty when no row has both a date and a genre.
    """
    if df.empty or "added_at" not in df.columns or "genres" not in df.columns:
        return pd.DataFrame()
    periods = _added_periods(df, freq)
    long_rows: list[tuple[Any, str]] = []
    for idx, period in periods.items():
        for genre in df.loc[idx, "genres"]:  # pyright: ignore[reportUnknownVariableType, reportArgumentType, reportCallIssue] — cell holds a list/ndarray of str
            long_rows.append((period, str(genre)))  # pyright: ignore[reportUnknownArgumentType]
    if not long_rows:
        return pd.DataFrame()
    long = pd.DataFrame(long_rows, columns=["period", "genre"])
    top = list(long["genre"].value_counts().head(top_n).index)
    long["genre"] = long["genre"].where(long["genre"].isin(top), "other")
    counts = long.groupby(["period", "genre"]).size().unstack(fill_value=0).sort_index()
    shares = counts.div(counts.sum(axis=1), axis=0)
    shares.index = pd.PeriodIndex(shares.index).to_timestamp()
    ordered = [g for g in top if g in shares.columns] + (["other"] if "other" in shares.columns else [])
    return shares[ordered]


def collaboration_edges(df: pd.DataFrame, min_weight: int = 1) -> pd.DataFrame:
    """Artist collaboration graph edges: two artists are connected when credited on the same track.

    Args:
        df: Track-level DataFrame with the list-valued ``artist_names`` column.
        min_weight: Minimum number of shared tracks for an edge to be kept.

    Returns:
        DataFrame with columns ``artist_a``, ``artist_b`` (alphabetical within each pair), ``weight`` (shared-track count), heaviest first.
        Empty when no track credits two or more distinct artists.
    """
    empty = pd.DataFrame({"artist_a": [], "artist_b": [], "weight": []})
    if df.empty or "artist_names" not in df.columns:
        return empty
    pair_counts: Counter[tuple[str, str]] = Counter()
    for names in df["artist_names"]:
        unique = sorted({str(n) for n in names})  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType] — cell holds a list/ndarray of str
        pair_counts.update(itertools.combinations(unique, 2))
    rows = [(a, b, w) for (a, b), w in pair_counts.items() if w >= min_weight]
    if not rows:
        return empty
    return pd.DataFrame(rows, columns=["artist_a", "artist_b", "weight"]).sort_values("weight", ascending=False, kind="stable").reset_index(drop=True)


def genre_cooccurrence(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Symmetric genre co-occurrence matrix over the top genres: how often two genres appear on the same track.

    The diagonal holds each genre's own track count, so the matrix doubles as a similarity map (off-diagonal) and a popularity readout (diagonal).

    Args:
        df: Track-level DataFrame with the list-valued ``genres`` column.
        top_n: Matrix dimension — the top genres by track count.

    Returns:
        Square DataFrame (index == columns == top genres, descending count) of co-occurrence counts. Empty when no track has genres.
    """
    if df.empty or "genres" not in df.columns:
        return pd.DataFrame()
    genre_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    for genres in df["genres"]:
        unique = sorted({str(g) for g in genres})  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType] — cell holds a list/ndarray of str
        genre_counts.update(unique)
        pair_counts.update(itertools.combinations(unique, 2))
    if not genre_counts:
        return pd.DataFrame()
    top = [genre for genre, _ in genre_counts.most_common(top_n)]
    matrix = pd.DataFrame(0, index=pd.Index(top), columns=pd.Index(top))
    for genre in top:
        matrix.loc[genre, genre] = genre_counts[genre]
    for (a, b), weight in pair_counts.items():
        if a in matrix.index and b in matrix.index:
            matrix.loc[a, b] = weight
            matrix.loc[b, a] = weight
    return matrix


def release_vs_added(df: pd.DataFrame) -> pd.DataFrame:
    """Pair each track's release year with the year it was added — new-release listening vs back-catalog digging.

    Args:
        df: Track-level DataFrame with ``track_id``, ``release_year``, ``added_at``, ``name``, and ``primary_artist_name`` columns.

    Returns:
        DataFrame with columns ``track_id`` (str, None for local files), ``release_year`` (int), ``added_year`` (int), ``track``, ``artist`` —
        one row per track that has both years. Empty (with the right columns) when nothing qualifies.
    """
    empty = pd.DataFrame({"track_id": [], "release_year": [], "added_year": [], "track": [], "artist": []})
    required = {"track_id", "release_year", "added_at", "name", "primary_artist_name"}
    if df.empty or not required.issubset(df.columns):
        return empty
    valid = df.dropna(subset=["release_year", "added_at"])
    if valid.empty:
        return empty
    added_year = pd.to_datetime(valid["added_at"], errors="coerce", utc=True).dt.year
    return pd.DataFrame(
        {
            "track_id": valid["track_id"].to_numpy(),
            "release_year": valid["release_year"].astype(int).to_numpy(),
            "added_year": added_year.to_numpy(),
            "track": valid["name"].to_numpy(),
            "artist": valid["primary_artist_name"].to_numpy(),
        }
    )
