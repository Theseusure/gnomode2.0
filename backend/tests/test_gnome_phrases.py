"""Smoke tests for tired-gnome banter phrases."""

from __future__ import annotations

from app.gnome_phrases import GNOME_TIRED_PHRASES, phrase_count, pick_gnome_phrase


def test_many_phrases():
    assert phrase_count() >= 80
    assert len(set(GNOME_TIRED_PHRASES)) == len(GNOME_TIRED_PHRASES)


def test_pick_avoids_last():
    first = GNOME_TIRED_PHRASES[0]
    for _ in range(30):
        assert pick_gnome_phrase(avoid=first) != first
