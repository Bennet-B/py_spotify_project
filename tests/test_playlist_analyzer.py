from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from spotify_project.analyzer import (
    Analyzer,
    GenreAnalyzer,
    PlaylistAnalyzer,
    TagAnalyzer,
    YearAnalyzer,
)
from spotify_project.models import Artist, Playlist, Track


class _ZeroCoverageWithSkipMessage(Analyzer):
    """Ad-hoc Analyzer reporting zero coverage AND carrying a skip_message.

    Both run_all and plot_all must skip this analyzer; if they call analyze() or plot() the methods raise to surface the bug.
    """

    title = "Flagged"
    skip_message = "no data; set X to enable"

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        return (0, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        raise AssertionError("analyze should not be called when skip applies")

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
        raise AssertionError("plot should not be called when skip applies")


class _ZeroCoverageWithoutSkipMessage(Analyzer):
    """Ad-hoc Analyzer with zero coverage but no skip_message — skip is opt-in, so it must still run."""

    title = "Unflagged"
    # skip_message left as default (None)

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        return (0, len(df))

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"k": [], "v": []})

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
        pass


class _AlwaysRunsAnalyzer(Analyzer):
    """Ad-hoc Analyzer reporting full coverage; used as a control alongside skip-eligible analyzers in plot_all tests."""

    title = "Always"

    def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
        n = len(df)
        return (n, n)

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"k": [1], "v": [1]})

    def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
        ax.bar([0], [1])  # pyright: ignore[reportUnknownMemberType]


class TestConstruction:
    """Tests for PlaylistAnalyzer.__init__ validation — analyzer uniqueness and custom-title support."""

    def test_rejects_duplicate_titles(self) -> None:
        """PlaylistAnalyzer fails fast when two analyzers share the same title.

        run_all keys results by title and plot_all renders one subplot per analyzer;
        a duplicate title would silently render the second analyzer's data under both subplots without raising.
        """
        with pytest.raises(ValueError, match="Analyzer titles must be unique"):
            PlaylistAnalyzer(
                df=pd.DataFrame(),
                analyzers=[YearAnalyzer(bucket_size=1), YearAnalyzer(bucket_size=10)],
            )

    def test_accepts_two_year_analyzers_with_distinct_titles(self) -> None:
        """Per-instance title override lets two same-class instances coexist.

        Without the override, registering two YearAnalyzer instances would collide on the class-level title. With the override, a custom title= kwarg gives each its own slot.
        """
        pa = PlaylistAnalyzer(
            df=pd.DataFrame(),
            analyzers=[
                YearAnalyzer(bucket_size=5, title="Years (5y)"),
                YearAnalyzer(bucket_size=10, title="Years (10y)"),
            ],
        )
        titles = [a.effective_title for a in pa.analyzers]
        assert titles == ["Years (5y)", "Years (10y)"]


class TestFromPlaylist:
    """Tests for PlaylistAnalyzer.from_playlist — the factory that materializes a track DataFrame from a Playlist domain object."""

    def test_exposes_artist_id_and_name_lists(self) -> None:
        """PlaylistAnalyzer.from_playlist surfaces parallel artist_ids/names lists.

        ArtistAnalyzer needs grouping-friendly columns (lists, not pipe-joined strings). This test pins the schema additions; if they regress, the analyzer breaks.
        """
        a1 = Artist(id="a1", name="Alice", tags=("rock",))
        a2 = Artist(id="a2", name="Bob", tags=("indie",))
        track = Track(
            id="t1",
            name="Song",
            artists=(a1, a2),
            album_name="Album",
            release_date="2020-01-01",
            duration_ms=200_000,
            explicit=False,
            added_at=datetime(2024, 6, 1, tzinfo=UTC),
            is_local=False,
        )
        playlist = Playlist(
            id="pl1",
            name="Test",
            owner_display_name="Bennet",
            public=True,
            collaborative=False,
            description="",
            tracks=(track,),
        )
        pa = PlaylistAnalyzer.from_playlist(playlist)
        row = pa.df.iloc[0]
        assert row["artist_ids"] == ["a1", "a2"]
        assert row["artist_names"] == ["Alice", "Bob"]

    def test_materializes_tags_column(self) -> None:
        """from_playlist materializes a `tags` column and a `genres` column on every track row."""
        artist = Artist(id="A1", name="Artist One", tags=("rock", "indie"))
        track = Track(
            id="T1",
            name="Track",
            artists=(artist,),
            album_name="Album",
            release_date="2020-01-01",
            duration_ms=200_000,
            explicit=False,
            added_at=None,
            is_local=False,
        )
        playlist = Playlist(
            id="P1",
            name="P",
            owner_display_name="",
            public=False,
            collaborative=False,
            description="",
            tracks=(track,),
        )
        pa = PlaylistAnalyzer.from_playlist(playlist)
        assert "tags" in pa.df.columns
        assert "genres" in pa.df.columns
        assert pa.df["tags"].iloc[0] == ["rock", "indie"]
        assert pa.df["genres"].iloc[0] == ["rock", "indie"]

    def test_unions_tags_across_all_track_artists(self) -> None:
        """A track's tags column unions every artist's tags, deduped, in primary-first order.

        A featured artist's tags belong on the track too — primary-only would lose data we already fetched.
        The genres column applies the same union shape but filters through the whitelist.
        """
        primary = Artist(id="A1", name="Primary", tags=("rock", "indie", "british"))
        feature = Artist(id="A2", name="Feature", tags=("pop", "indie", "00s"))
        track = Track(
            id="T1",
            name="Track",
            artists=(primary, feature),
            album_name="Album",
            release_date="2020-01-01",
            duration_ms=200_000,
            explicit=False,
            added_at=None,
            is_local=False,
        )
        playlist = Playlist(
            id="P1",
            name="P",
            owner_display_name="",
            public=False,
            collaborative=False,
            description="",
            tracks=(track,),
        )
        pa = PlaylistAnalyzer.from_playlist(playlist)
        # Primary's tags come first; feature's contributions follow, with duplicates ("indie") dropped at first occurrence.
        assert pa.df["tags"].iloc[0] == ["rock", "indie", "british", "pop", "00s"]
        # genres column: same union shape, filtered through the whitelist. "indie" is whitelisted; "british" and "00s" aren't.
        assert pa.df["genres"].iloc[0] == ["rock", "indie", "pop"]

    def test_default_analyzers_include_tag_analyzer(self) -> None:
        """from_playlist's default analyzer list includes a TagAnalyzer."""
        empty_playlist = Playlist(
            id="P",
            name="P",
            owner_display_name="",
            public=False,
            collaborative=False,
            description="",
            tracks=(),
        )
        pa = PlaylistAnalyzer.from_playlist(empty_playlist)
        assert any(isinstance(a, TagAnalyzer) for a in pa.analyzers)


class TestRunAll:
    """Tests for PlaylistAnalyzer.run_all — the orchestrator that drives each analyzer's analyze() in turn."""

    def test_skips_analyzer_with_zero_coverage_and_skip_message(self) -> None:
        """run_all skips an analyzer whose coverage is zero AND whose skip_message is set.

        The skipped analyzer's analyze() must not be called — raising in there asserts the skip path took effect.
        """
        df = pd.DataFrame({"x": [1, 2, 3]})
        pa = PlaylistAnalyzer(df=df, analyzers=[_ZeroCoverageWithSkipMessage()])
        result = pa.run_all()
        assert "Flagged" not in result

    def test_runs_analyzer_with_zero_coverage_when_no_skip_message(self) -> None:
        """run_all still runs an analyzer with zero coverage when skip_message is None.

        Skip is opt-in: only analyzers that explicitly set skip_message are eligible to be skipped.
        """
        df = pd.DataFrame({"x": [1, 2, 3]})
        pa = PlaylistAnalyzer(df=df, analyzers=[_ZeroCoverageWithoutSkipMessage()])
        result = pa.run_all()
        assert "Unflagged" in result

    def test_does_not_skip_on_empty_playlist(self) -> None:
        """An entirely empty DataFrame means "empty playlist", not "data source absent" — skip-eligible analyzers still run.

        Skipping would log the misleading "set LASTFM_API_KEY" hint when the actual cause is zero tracks.
        """
        pa = PlaylistAnalyzer(df=pd.DataFrame(), analyzers=[TagAnalyzer()])
        result = pa.run_all()
        assert "Top Tags" in result
        assert result["Top Tags"].empty


class TestPlotAll:
    """Tests for PlaylistAnalyzer.plot_all — subplot orchestration and skip behavior."""

    def test_with_no_analyzers_does_not_crash(self) -> None:
        """plot_all returns early when the analyzer list is empty (no subplots to render)."""
        pa = PlaylistAnalyzer(df=pd.DataFrame(), analyzers=[])
        pa.plot_all(Figure())

    def test_skips_zero_coverage_analyzer(self) -> None:
        """plot_all skips an analyzer with zero coverage and a skip_message, rendering only the eligible analyzers' subplots."""
        df = pd.DataFrame({"x": [1, 2, 3]})
        pa = PlaylistAnalyzer(
            df=df,
            analyzers=[_ZeroCoverageWithSkipMessage(), _AlwaysRunsAnalyzer()],
        )
        fig = Figure()
        pa.plot_all(fig)  # should not raise
        # One subplot, not two:
        assert len(fig.axes) == 1


class TestToParquet:
    """Tests for PlaylistAnalyzer.to_parquet — the on-disk DataFrame export."""

    def test_round_trip_preserves_schema(self, tmp_path: Path) -> None:
        """to_parquet → read_parquet preserves columns and values exactly.

        Especially important for the list columns (``artist_ids``, ``artist_names``, ``genres``) which parquet stores as nested types.
        """
        df = pd.DataFrame(
            [
                {
                    "track_id": "t1",
                    "name": "Song",
                    "primary_artist_id": "a1",
                    "primary_artist_name": "Alice",
                    "artist_ids": ["a1"],
                    "artist_names": ["Alice"],
                    "album_name": "Album",
                    "release_date": "2020-01-01",
                    "release_year": pd.array([2020], dtype="Int64")[0],
                    "duration_ms": 200_000,
                    "duration_min": 200_000 / 60_000,
                    "explicit": False,
                    "added_at": pd.Timestamp("2024-06-01", tz="UTC"),
                    "is_local": False,
                    "genres": ["rock"],
                }
            ]
        )
        pa = PlaylistAnalyzer(df=df, analyzers=[])
        out = tmp_path / "playlist.parquet"
        pa.to_parquet(out)
        assert out.exists()

        reloaded = pd.read_parquet(out)
        assert list(reloaded.columns) == list(df.columns)
        assert reloaded.iloc[0]["track_id"] == "t1"
        assert list(reloaded.iloc[0]["artist_ids"]) == ["a1"]
        assert list(reloaded.iloc[0]["genres"]) == ["rock"]

    def test_round_trip_preserves_tag_and_genre_coverage(self, tmp_path: Path) -> None:
        """Tag/Genre coverage still detects data after a parquet round trip.

        read_parquet materializes list columns as numpy arrays; coverage() used to isinstance-check for list and report zero, which made run_all skip both analyzers on a reloaded DataFrame.
        """
        df = pd.DataFrame([{"track_id": "t1", "tags": ["rock", "indie"], "genres": ["rock"]}])
        pa = PlaylistAnalyzer(df=df, analyzers=[])
        out = tmp_path / "roundtrip.parquet"
        pa.to_parquet(out)
        reloaded = pd.read_parquet(out)
        assert TagAnalyzer().coverage(reloaded) == (1, 1)
        assert GenreAnalyzer().coverage(reloaded) == (1, 1)
