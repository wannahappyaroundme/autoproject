"""Mission planning: optimize bin visit order using nearest-neighbor TSP heuristic."""
import math


def optimize_visit_order(
    start: tuple[float, float],
    bin_positions: dict[int, tuple[float, float]],
) -> list[int]:
    """Nearest-neighbor heuristic for TSP.

    Args:
        start: (x, y) robot starting position
        bin_positions: {bin_id: (x, y)} map of bins to visit

    Returns:
        Ordered list of bin_ids for optimal visit sequence.
    """
    if not bin_positions:
        return []

    remaining = set(bin_positions.keys())
    ordered = []
    current = start

    while remaining:
        nearest_id = None
        nearest_dist = float("inf")
        for bid in remaining:
            pos = bin_positions[bid]
            dist = math.sqrt((pos[0] - current[0]) ** 2 + (pos[1] - current[1]) ** 2)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_id = bid

        ordered.append(nearest_id)
        current = bin_positions[nearest_id]
        remaining.remove(nearest_id)

    return ordered
