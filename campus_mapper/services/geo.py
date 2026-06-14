"""
Geographic utilities (distance calculation, sampling points, etc.).
"""

from __future__ import annotations

import math
from typing import List, Tuple


def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in kilometers."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def sample_points_along_segment(
    lat1: float, lng1: float, lat2: float, lng2: float, num_points: int = 3
) -> List[Tuple[float, float]]:
    """Return points sampled along a segment including endpoints."""
    points: List[Tuple[float, float]] = []
    for i in range(num_points):
        fraction = i / (num_points - 1) if num_points > 1 else 0.5
        lat = lat1 + (lat2 - lat1) * fraction
        lng = lng1 + (lng2 - lng1) * fraction
        points.append((lat, lng))
    return points

