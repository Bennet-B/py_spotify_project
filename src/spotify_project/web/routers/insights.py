"""Insight endpoints — thin wrappers serving the pure computations in ``spotify_project.insights`` as tidy typed rows.

The frontend owns all Plotly configuration; these endpoints only ship plot-ready domain rows, so chart selections map straight back to
domain values (labels, years, artist ids, track ids).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

import pandas as pd
from fastapi import APIRouter, Query

from ... import insights
from ..deps import DatasetStoreDep
from ..schemas import (
    AdditionRow,
    AdditionsResponse,
    ArtistCountRow,
    ArtistsResponse,
    DiscoveryResponse,
    DiscoveryRow,
    LabelCountRow,
    LabelsResponse,
    ReleaseVsAddedResponse,
    ReleaseVsAddedRow,
    SeasonalResponse,
    SeasonalRow,
    YearCountRow,
    YearsResponse,
)

router = APIRouter(prefix="/playlists/{playlist_id}/insights", tags=["insights"])

type Freq = Literal["W", "M", "Q", "Y"]


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame rows as plain dicts for pydantic model construction."""
    return cast("list[dict[str, Any]]", df.to_dict("records"))


@router.get("/labels")
def labels(playlist_id: str, store: DatasetStoreDep, field: Literal["genres", "tags"] = "genres", top_n: Annotated[int, Query(ge=1, le=200)] = 30) -> LabelsResponse:
    """Tag/genre frequency bars — the primary rule-helper chart (bar click → tag filter)."""
    dataset = store.require(playlist_id)
    rows = insights.label_frequencies(dataset.df, field=field, top_n=top_n)
    return LabelsResponse(field=field, rows=[LabelCountRow(**rec) for rec in _records(rows)])


@router.get("/years")
def years(playlist_id: str, store: DatasetStoreDep) -> YearsResponse:
    """Tracks per release year, pre-binned server-side so a bar click/box-select maps to exact years."""
    dataset = store.require(playlist_id)
    return YearsResponse(rows=[YearCountRow(**rec) for rec in _records(insights.year_counts(dataset.df))])


@router.get("/additions")
def additions(playlist_id: str, store: DatasetStoreDep, freq: Freq = "M") -> AdditionsResponse:
    """Library growth: additions per period plus cumulative tracks/hours."""
    dataset = store.require(playlist_id)
    rows = insights.additions_over_time(dataset.df, freq=freq)
    return AdditionsResponse(freq=freq, rows=[AdditionRow(**rec) for rec in _records(rows)])


@router.get("/discovery")
def discovery(playlist_id: str, store: DatasetStoreDep, freq: Freq = "M") -> DiscoveryResponse:
    """Artist discovery waves: how many artists enter the library for the first time per period."""
    dataset = store.require(playlist_id)
    rows = insights.discovery_waves(dataset.df, freq=freq)
    return DiscoveryResponse(freq=freq, rows=[DiscoveryRow(**rec) for rec in _records(rows)])


@router.get("/seasonal")
def seasonal(playlist_id: str, store: DatasetStoreDep) -> SeasonalResponse:
    """Additions by calendar month aggregated across years (always 12 rows)."""
    dataset = store.require(playlist_id)
    return SeasonalResponse(rows=[SeasonalRow(**rec) for rec in _records(insights.seasonal_profile(dataset.df))])


@router.get("/artists")
def artists(playlist_id: str, store: DatasetStoreDep, genre: Annotated[list[str] | None, Query()] = None, top_n: Annotated[int, Query(ge=1, le=200)] = 25) -> ArtistsResponse:
    """Track counts per credited artist; repeatable ``genre`` params implement the cascading genre→artist re-scope."""
    dataset = store.require(playlist_id)
    genres = genre or []
    rows = insights.artist_track_counts(dataset.df, genres=genres, top_n=top_n)
    return ArtistsResponse(scoped_to_genres=genres, rows=[ArtistCountRow(**rec) for rec in _records(rows)])


@router.get("/release-vs-added")
def release_vs_added(playlist_id: str, store: DatasetStoreDep) -> ReleaseVsAddedResponse:
    """Release-year vs added-year scatter rows; carries track ids so a lasso selection can become a playlist."""
    dataset = store.require(playlist_id)
    rows = insights.release_vs_added(dataset.df)
    return ReleaseVsAddedResponse(rows=[ReleaseVsAddedRow(**rec) for rec in _records(rows)])
