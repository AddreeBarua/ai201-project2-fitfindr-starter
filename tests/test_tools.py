"""
tests/test_tools.py

Unit tests for the three FitFindr tools, covering both happy paths
and the failure modes documented in planning.md.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_matches_compound_size():
    # "M" should match a listing with size "S/M"
    results = search_listings("baby tee", size="M", max_price=50)
    assert len(results) > 0
    for item in results:
        assert "m" in item["size"].lower()


# ── suggest_outfit ───────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 0


def test_suggest_outfit_empty_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    outfit = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 0   # general styling advice, not empty


# ── create_fit_card ──────────────────────────────────────────────────────────

def test_create_fit_card_with_valid_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    fit_card = create_fit_card(
        "Pair with high-waisted jeans and white sneakers.",
        results[0],
    )
    assert isinstance(fit_card, str)
    assert len(fit_card.strip()) > 0


def test_create_fit_card_empty_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    fit_card = create_fit_card("", results[0])
    assert isinstance(fit_card, str)
    assert len(fit_card.strip()) > 0
    assert "couldn't generate" in fit_card.lower()


def test_create_fit_card_whitespace_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    fit_card = create_fit_card("   ", results[0])
    assert "couldn't generate" in fit_card.lower()