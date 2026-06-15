"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,                # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

_SIZE_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "xxs"}

_FILLER_PATTERNS = [
    r"\bi'?m looking for\b",
    r"\blooking for\b",
    r"\bi want\b",
    r"\bunder\b",
    r"\bor less\b",
    r"\bin\b",
    r"\bthe\b",
    r"\ba\b",
    r"\ban\b",
]


def _parse_query(query: str) -> dict:
    """
    Parse a natural language query into description, size, and max_price
    using regex — no LLM call.

    Returns a dict with keys: description (str), size (str | None),
    max_price (float | None).
    """
    parsed = {"description": query, "size": None, "max_price": None}

    # max_price: look for a dollar amount, e.g. "$30" or "$30.00"
    price_match = re.search(r"\$(\d+(?:\.\d+)?)", query)
    if price_match:
        parsed["max_price"] = float(price_match.group(1))

    # size: prefer an explicit "size X" pattern (e.g. "size M", "size 8")
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)\b", query, re.IGNORECASE)
    if size_match:
        parsed["size"] = size_match.group(1).upper()
    else:
        # fall back to a standalone size token (XS, S, M, L, XL, XXL)
        for word in re.findall(r"\b\w+\b", query):
            if word.lower() in _SIZE_TOKENS:
                parsed["size"] = word.upper()
                break

    # Build the description by stripping out the price phrase, the size
    # phrase, and common filler words.
    description = query
    description = re.sub(r"\$\d+(?:\.\d+)?", "", description)
    description = re.sub(
        r"\bsize\s+[A-Za-z0-9/]+\b", "", description, flags=re.IGNORECASE
    )

    # If the size came from a standalone token (not "size X"), strip that
    # token out of the description too.
    if size_match is None and parsed["size"]:
        description = re.sub(
            r"\b" + re.escape(parsed["size"]) + r"\b",
            "",
            description,
            flags=re.IGNORECASE,
        )

    for pattern in _FILLER_PATTERNS:
        description = re.sub(pattern, "", description, flags=re.IGNORECASE)

    # Collapse extra whitespace and stray punctuation left behind
    description = re.sub(r"\s+", " ", description)
    description = description.strip(" ,.")

    parsed["description"] = description

    return parsed


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: initialize session
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into description / size / max_price
    session["parsed"] = _parse_query(query)

    # Step 3: search listings using the parsed parameters
    session["search_results"] = search_listings(
        description=session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )

    # If no results, set an error and stop — do NOT call suggest_outfit
    if not session["search_results"]:
        size_part = f", size {session['parsed']['size']}" if session["parsed"]["size"] else ""
        price_part = (
            f" under ${session['parsed']['max_price']:.0f}"
            if session["parsed"]["max_price"] is not None
            else ""
        )
        session["error"] = (
            f"No listings found for \"{session['parsed']['description']}\""
            f"{size_part}{price_part}. Try removing the size or price filter, "
            f"or rewording your description."
        )
        return session

    # Step 4: select the top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: get an outfit suggestion for the selected item
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )

    # Step 6: generate a shareable fit card
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    # Step 7: return the completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Parsed: {session['parsed']}")
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Parsed: {session2['parsed']}")
    print(f"Error message: {session2['error']}")