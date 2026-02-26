"""Google Autocomplete keyword suggestions — no API key needed."""

import requests

AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"


def google_autocomplete(query: str, lang: str = "en") -> list[str]:
    """Get keyword suggestions from Google Autocomplete."""
    try:
        resp = requests.get(
            AUTOCOMPLETE_URL,
            params={
                "client": "firefox",
                "q": query,
                "hl": lang,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response format: [query, [suggestion1, suggestion2, ...]]
        if isinstance(data, list) and len(data) >= 2:
            return data[1]
        return []
    except Exception:
        return []


def people_also_search(query: str, lang: str = "en") -> list[str]:
    """Get expanded suggestions using question/comparison modifiers."""
    modifiers = ["how", "why", "what", "vs", "best", "for"]
    seen = set()
    results = []

    for mod in modifiers:
        suggestions = google_autocomplete(f"{query} {mod}", lang=lang)
        for s in suggestions:
            lower = s.lower()
            if lower not in seen:
                seen.add(lower)
                results.append(s)

    return results


def keyword_ideas(seed_keywords: list[str], lang: str = "en") -> list[dict]:
    """Get autocomplete suggestions for each seed keyword."""
    results = []
    seen = set()

    for seed in seed_keywords:
        suggestions = google_autocomplete(seed, lang=lang)
        for s in suggestions:
            lower = s.lower()
            if lower not in seen:
                seen.add(lower)
                results.append({"keyword": s, "source": seed})

    return results
