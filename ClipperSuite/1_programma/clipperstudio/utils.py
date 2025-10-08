"""Utility helpers for ClipperStudio."""
from __future__ import annotations

import math
import random
from datetime import timedelta
from typing import Iterable, List, Optional, Sequence, Tuple


def format_timedelta(seconds: float) -> str:
    """Return a human readable string for a duration in seconds."""

    seconds = int(max(0, round(seconds)))
    delta = timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: List[str] = []
    if delta.days:
        parts.append(f"{delta.days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def generate_clip_plan(
    duration: float,
    clip_duration: int,
    overlap: int,
    final_min: int,
    final_max: int,
) -> List[Tuple[float, float]]:
    """Split ``duration`` seconds into clips of approximately ``clip_duration``.

    The final clip is adjusted so that its duration falls within
    ``[final_min, final_max]``.
    """

    if duration <= 0:
        return []

    clip_duration = max(1, clip_duration)
    overlap = max(0, overlap)
    clips: List[Tuple[float, float]] = []
    start = 0.0
    while start < duration:
        end = start + clip_duration
        clips.append((start, min(end, duration)))
        start = end - overlap
        if start >= duration:
            break

    if not clips:
        return []

    # Adjust final clip length to comply with the [final_min, final_max] rule.
    final_start, final_end = clips[-1]
    final_length = final_end - final_start
    if final_length < final_min and len(clips) > 1:
        deficit = final_min - final_length
        final_start = max(0.0, final_start - deficit)
    elif final_length > final_max:
        final_start = final_end - final_max
    clips[-1] = (final_start, final_end)
    return clips


def randomise_interval(
    base_seconds: int, variation_seconds: int, *, rng: Optional[random.Random] = None
) -> int:
    """Return a randomised interval based on ``base_seconds``.

    The value is sampled uniformly in ``[base_seconds - variation, base_seconds +
    variation]`` and is always clamped to ``>= 0``.  ``rng`` can be supplied to
    get deterministic behaviour in tests.
    """

    rng = rng or random
    low = base_seconds - variation_seconds
    high = base_seconds + variation_seconds
    sampled = rng.randint(int(low), int(high))
    return max(0, sampled)


def cumulative(sequence: Sequence[int]) -> Iterable[int]:
    """Yield the cumulative sum of ``sequence``."""

    total = 0
    for item in sequence:
        total += item
        yield total
