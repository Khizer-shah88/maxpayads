"""Unit tests for traffic routing helpers."""
import pytest
from collections import Counter
from app.services.traffic_router import select_weighted_landing_page


def test_select_weighted_landing_page_empty():
    assert select_weighted_landing_page([]) is None


def test_select_weighted_landing_page_single():
    pages = [{"name": "A", "weight": 50}]
    assert select_weighted_landing_page(pages)["name"] == "A"


def test_select_weighted_landing_page_50_50_distribution():
    pages = [
        {"name": "A", "weight": 50},
        {"name": "B", "weight": 50},
    ]
    counts = Counter()
    for _ in range(5000):
        picked = select_weighted_landing_page(pages)
        counts[picked["name"]] += 1
    # With 5000 trials, each bucket should land near 50% (±5% tolerance).
    assert 0.45 <= counts["A"] / 5000 <= 0.55
    assert 0.45 <= counts["B"] / 5000 <= 0.55


def test_select_weighted_landing_page_skips_zero_weight():
    pages = [
        {"name": "A", "weight": 0},
        {"name": "B", "weight": 100},
    ]
    for _ in range(100):
        assert select_weighted_landing_page(pages)["name"] == "B"


def test_select_weighted_landing_page_uneven_weights():
    pages = [
        {"name": "A", "weight": 80},
        {"name": "B", "weight": 20},
    ]
    counts = Counter()
    for _ in range(5000):
        picked = select_weighted_landing_page(pages)
        counts[picked["name"]] += 1
    assert 0.70 <= counts["A"] / 5000 <= 0.90
    assert 0.10 <= counts["B"] / 5000 <= 0.30
