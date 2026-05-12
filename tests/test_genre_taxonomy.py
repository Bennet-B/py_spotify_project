from __future__ import annotations

from spotify_project.genre_taxonomy import GENRE_WHITELIST, filter_to_genres


def test_filter_to_genres_keeps_whitelisted_tags_in_order() -> None:
    result = filter_to_genres(("rock", "seen live", "indie", "british"))
    assert result == ["rock", "indie"]


def test_filter_to_genres_returns_empty_for_empty_input() -> None:
    assert filter_to_genres(()) == []


def test_filter_to_genres_drops_unknown_tags() -> None:
    assert filter_to_genres(("seen live", "british", "00s")) == []


def test_filter_to_genres_preserves_descending_weight_order() -> None:
    # If both rock and indie are in the whitelist, the order in the output
    # must match the order in the input (Last.fm returns descending weight).
    assert filter_to_genres(("indie", "rock")) == ["indie", "rock"]
    assert filter_to_genres(("rock", "indie")) == ["rock", "indie"]


def test_genre_whitelist_is_frozenset_of_str() -> None:
    assert isinstance(GENRE_WHITELIST, frozenset)
    assert all(isinstance(g, str) for g in GENRE_WHITELIST)
    # Spot-check that a defensible baseline is present.
    for g in ("rock", "pop", "indie", "electronic", "jazz", "metal"):
        assert g in GENRE_WHITELIST
