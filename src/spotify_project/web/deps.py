"""Dependency providers — the single place the web layer constructs core objects.

This module is the multi-user seam. Every router obtains its ``SpotifyClient``, ``FileCache``, ``JobRegistry``, and ``DatasetStore`` through these
providers, so a hosted multi-account deployment later only swaps provider internals (per-session OAuth, per-user cache roots, user-scoped registries and
stores) while routers stay untouched. Today each provider returns a lazily-created process-wide singleton, which is exactly right for local single-user use.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from ..cache import FileCache
from ..client import SpotifyClient
from ..lastfm_client import LastFmClient
from .dataset import DatasetStore
from .jobs import JobRegistry


@lru_cache(maxsize=1)
def get_cache() -> FileCache:
    """Return the shared API response cache."""
    return FileCache()


@lru_cache(maxsize=1)
def get_client() -> SpotifyClient:
    """Return the authenticated Spotify client.

    spotipy's browser-based OAuth flow may trigger on the first API call (not at construction) when no valid token is cached.
    """
    cache = get_cache()
    return SpotifyClient.from_env(cache, genre_enricher=LastFmClient.from_env(cache=cache))


@lru_cache(maxsize=1)
def get_job_registry() -> JobRegistry:
    """Return the process-wide background job registry."""
    return JobRegistry()


@lru_cache(maxsize=1)
def get_dataset_store() -> DatasetStore:
    """Return the process-wide store of loaded playlist datasets."""
    return DatasetStore()


CacheDep = Annotated[FileCache, Depends(get_cache)]
ClientDep = Annotated[SpotifyClient, Depends(get_client)]
JobRegistryDep = Annotated[JobRegistry, Depends(get_job_registry)]
DatasetStoreDep = Annotated[DatasetStore, Depends(get_dataset_store)]
