"""Fleet geo helpers."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def simplify_coords(coords: list[list[float]], max_points: int = 2000) -> list[list[float]]:
    if len(coords) <= max_points:
        return coords
    step = max(1, len(coords) // max_points)
    return [coords[i] for i in range(0, len(coords), step)]
