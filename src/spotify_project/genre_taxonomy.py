from __future__ import annotations

GENRE_WHITELIST: frozenset[str] = frozenset(
    {
        # Widely-recognized genre names, all lowercase, one canonical form per concept.
        # LastFmClient pre-processes tags (lowercase + strip + TAG_SYNONYMS canonicalization + dedupe), so this filter is a pure membership check.
        # When adding entries: pick the form that matches LastFmClient.TAG_SYNONYMS' RHS, not a synonym handled there.
        "rock",
        "pop",
        "indie",
        "indie pop",
        "indie rock",
        "alternative",
        "alternative rock",
        "metal",
        "heavy metal",
        "black metal",
        "death metal",
        "doom metal",
        "thrash metal",
        "metalcore",
        "hardcore",
        "punk",
        "post-punk",
        "pop punk",
        "ska",
        "emo",
        "jazz",
        "blues",
        "soul",
        "funk",
        "r&b",
        "rap",
        "hip hop",
        "trap",
        "grime",
        "electronic",
        "electronica",
        "house",
        "deep house",
        "tech house",
        "techno",
        "trance",
        "ambient",
        "drum and bass",
        "dubstep",
        "edm",
        "idm",
        "synthwave",
        "synthpop",
        "electropop",
        "industrial",
        "classical",
        "baroque",
        "opera",
        "orchestral",
        "soundtrack",
        "score",
        "folk",
        "folk rock",
        "country",
        "americana",
        "bluegrass",
        "reggae",
        "dub",
        "dancehall",
        "disco",
        "post-rock",
        "post-metal",
        "shoegaze",
        "dream pop",
        "noise",
        "experimental",
        "psychedelic",
        "psychedelic rock",
        "garage rock",
        "indietronica",
        "lo-fi",
        "j-pop",
        "k-pop",
        "j-rock",
        "gospel",
        "world",
        "latin",
        "tango",
        "salsa",
        "bossa nova",
        "afrobeat",
        "new wave",
        "no wave",
        "math rock",
        "progressive rock",
        "prog",
        "singer-songwriter",
        "acoustic",
    }
)


def filter_to_genres(tags: tuple[str, ...]) -> list[str]:
    """Return the whitelisted subset of ``tags``, preserving input order.

    Tags are expected lowercase (lowercasing happens upstream in ``LastFmClient.fetch_artist_tags``), so the filter is a pure membership check with no normalization.

    Args:
        tags: Lowercased tags in descending-weight order, as stored on Artist.

    Returns:
        A new list containing only the tags that appear in GENRE_WHITELIST, in the same order they appeared in ``tags``.
    """
    return [t for t in tags if t in GENRE_WHITELIST]
