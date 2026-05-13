from __future__ import annotations

import pytest

from spotify_project.genre_taxonomy import GENRE_WHITELIST, filter_to_genres


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        # Whitelist hits stay in input order; non-genre tags ("seen live", "british") are dropped.
        (("rock", "seen live", "indie", "british"), ["rock", "indie"]),
        # Empty input → empty output.
        ((), []),
        # No false positives: a fully unknown tag set produces nothing.
        (("seen live", "british", "00s"), []),
        # Last.fm returns descending-weight order; both directions must round-trip unchanged.
        (("indie", "rock"), ["indie", "rock"]),
        (("rock", "indie"), ["rock", "indie"]),
        # Multi-word whitelist entries match as a single tag (not via substring of "hip" + "hop").
        (("hip hop", "rock"), ["hip hop", "rock"]),
        # Filter is case-sensitive — docstring contract is "tags expected lowercase", so "Rock" / "INDIE" intentionally fall through (LastFmClient handles lowercasing upstream).
        (("Rock", "rock", "INDIE"), ["rock"]),
    ],
    ids=[
        "mixed_whitelist_and_noise",
        "empty",
        "all_unknown",
        "order_indie_first",
        "order_rock_first",
        "multi_word_genre",
        "case_sensitive_only_lowercase_matches",
    ],
)
def test_filter_to_genres(tags: tuple[str, ...], expected: list[str]) -> None:
    """filter_to_genres keeps whitelisted tags in input order; no case folding, no dedupe."""
    assert filter_to_genres(tags) == expected


def test_genre_whitelist_is_frozenset_of_str() -> None:
    """GENRE_WHITELIST is an immutable string set with a defensible baseline of common genres."""
    assert isinstance(GENRE_WHITELIST, frozenset)
    assert all(isinstance(g, str) for g in GENRE_WHITELIST)
    # Spot-check that a defensible baseline is present.
    for g in ("rock", "pop", "indie", "electronic", "jazz", "metal"):
        assert g in GENRE_WHITELIST
