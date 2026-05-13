from __future__ import annotations

from pathlib import Path

import pandas as pd

from spotify_project.analyzer import PlaylistAnalyzer


def test_to_parquet_round_trip_preserves_schema(tmp_path: Path) -> None:
    """to_parquet → read_parquet preserves columns and values exactly.

    Especially important for the list columns (``artist_ids``, ``artist_names``,
    ``genres``) which parquet stores as nested types.
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


def test_run_all_skips_analyzer_with_zero_coverage_and_skip_message() -> None:
    import pandas as pd
    from matplotlib.axes import Axes

    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer

    class FlaggedZeroCoverage(Analyzer):
        title = "Flagged"
        skip_message = "no data; set X to enable"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            raise AssertionError("analyze should not be called when skip applies")

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            raise AssertionError("plot should not be called when skip applies")

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[FlaggedZeroCoverage()])
    result = pa.run_all()
    assert "Flagged" not in result


def test_run_all_runs_analyzer_with_zero_coverage_when_no_skip_message() -> None:
    import pandas as pd
    from matplotlib.axes import Axes

    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer

    class UnflaggedZeroCoverage(Analyzer):
        title = "Unflagged"
        # skip_message left as default (None)

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({"k": [], "v": []})

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            pass

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[UnflaggedZeroCoverage()])
    result = pa.run_all()
    assert "Unflagged" in result  # still runs — opt-in skip only


def test_plot_all_skips_zero_coverage_analyzer() -> None:
    import pandas as pd
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from spotify_project.analyzer import Analyzer, PlaylistAnalyzer

    class FlaggedZeroCoverage(Analyzer):
        title = "Flagged"
        skip_message = "no data"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            return (0, len(df))

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            raise AssertionError("analyze should not be called when skip applies")

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            raise AssertionError("plot should not be called when skip applies")

    class AlwaysRuns(Analyzer):
        title = "Always"

        def coverage(self, df: pd.DataFrame) -> tuple[int, int]:
            n = len(df)
            return (n, n)

        def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame({"k": [1], "v": [1]})

        def plot(self, ax: Axes, summary: pd.DataFrame, *, color: object = None) -> None:
            ax.bar([0], [1])  # pyright: ignore[reportUnknownMemberType]

    df = pd.DataFrame({"x": [1, 2, 3]})
    pa = PlaylistAnalyzer(df=df, analyzers=[FlaggedZeroCoverage(), AlwaysRuns()])
    fig = Figure()
    pa.plot_all(fig)  # should not raise
    # One subplot, not two:
    assert len(fig.axes) == 1


def test_from_playlist_materializes_tags_column() -> None:
    from spotify_project.analyzer import PlaylistAnalyzer
    from spotify_project.models import Artist, Playlist, Track

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


def test_from_playlist_unions_tags_across_all_track_artists() -> None:
    # A featured artist's tags belong on the track too — primary-only would lose data we already fetched.
    from spotify_project.analyzer import PlaylistAnalyzer
    from spotify_project.models import Artist, Playlist, Track

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


def test_from_playlist_default_analyzers_include_tag_analyzer() -> None:
    from spotify_project.analyzer import PlaylistAnalyzer, TagAnalyzer
    from spotify_project.models import Playlist

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
