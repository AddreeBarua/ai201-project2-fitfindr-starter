"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Filter by max_price (if provided)
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # Filter by size (if provided) — case-insensitive substring match
    # so a query for "M" matches a listing size of "S/M"
    if size is not None:
        size_lower = size.lower()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Score remaining listings by keyword overlap with `description`
    description_words = description.lower().split()

    scored = []
    for item in listings:
        searchable_text = " ".join([
            item["title"],
            item["description"],
            item["category"],
            " ".join(item["style_tags"]),
        ]).lower()

        score = sum(1 for word in description_words if word in searchable_text)

        if score > 0:
            scored.append((score, item))

    # Sort by score, highest first
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [item for score, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    # Describe the new item for the prompt
    item_description = (
        f"{new_item['title']} — {new_item['description']} "
        f"(category: {new_item['category']}, colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])}, condition: {new_item['condition']})"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — ask for general styling advice
        prompt = (
            f"A user is considering buying this secondhand item:\n"
            f"{item_description}\n\n"
            f"They don't have any wardrobe items logged yet. Give them general "
            f"styling advice for this piece: what kinds of items pair well with it, "
            f"what overall vibe or aesthetic it suits, and 1-2 example outfit ideas "
            f"using items they likely already own (e.g. 'jeans', 'white sneakers'). "
            f"Keep it conversational and specific, 3-5 sentences."
        )
    else:
        # Format wardrobe items as bullets
        wardrobe_bullets = "\n".join(
            f"- {item['name']} ({item['category']}, "
            f"colors: {', '.join(item['colors'])}, "
            f"style: {', '.join(item['style_tags'])})"
            + (f" — {item['notes']}" if item.get("notes") else "")
            for item in wardrobe_items
        )

        prompt = (
            f"A user is considering buying this secondhand item:\n"
            f"{item_description}\n\n"
            f"Here is their current wardrobe:\n"
            f"{wardrobe_bullets}\n\n"
            f"Suggest 1-2 complete outfit combinations that pair the new item "
            f"with specific named pieces from their wardrobe. Be specific about "
            f"which wardrobe items to use and how to style them together "
            f"(e.g. tucked, layered, rolled sleeves). Keep it conversational, "
            f"3-5 sentences."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a friendly, knowledgeable thrift fashion stylist."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return (
            "Couldn't generate a fit card — no outfit suggestion was provided. "
            "Try running suggest_outfit first."
        )

    client = _get_groq_client()

    prompt = (
        f"Write a short, casual Instagram/TikTok caption (2-4 sentences) for an "
        f"OOTD (outfit of the day) post featuring a thrifted item.\n\n"
        f"The item: \"{new_item['title']}\" — bought for ${new_item['price']:.0f} "
        f"on {new_item['platform']}.\n\n"
        f"The outfit: {outfit}\n\n"
        f"Write it like a real person would caption their post — casual, "
        f"first-person, a little excited, maybe with an emoji or two. "
        f"Mention the item name, price, and platform naturally, each only once. "
        f"Capture the vibe of the outfit in specific terms. Don't make it sound "
        f"like a product description."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You write authentic, casual social media captions for thrifted fashion finds."},
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
    )

    return response.choices[0].message.content