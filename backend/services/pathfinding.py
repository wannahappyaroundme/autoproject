"""A* pathfinding algorithm on a 2D grid.

Designed to mirror Nav2's NavFn planner concepts:
- Grid = OccupancyGrid
- Cell cost with inflation = Costmap2D InflationLayer
- 8-directional movement
"""
import heapq
import math


def astar(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    width: int,
    height: int,
    inflation_radius: int = 2,
) -> list[tuple[int, int]]:
    """Find shortest path using A* with obstacle inflation.

    Args:
        grid: 2D grid where 0=free, 1=obstacle
        start: (x, y) start position
        goal: (x, y) goal position
        width: grid width
        height: grid height
        inflation_radius: cells around obstacles with increased cost (mimics Nav2 InflationLayer)

    Returns:
        List of (x, y) coordinates from start to goal, or empty list if no path.
    """
    sx, sy = _clamp(start[0], start[1], width, height)
    gx, gy = _clamp(goal[0], goal[1], width, height)

    if grid[sy][sx] == 1:
        sx, sy = _find_nearest_free(grid, sx, sy, width, height)
    if grid[gy][gx] == 1:
        gx, gy = _find_nearest_free(grid, gx, gy, width, height)

    # Build cost grid with inflation
    cost_grid = _build_cost_grid(grid, width, height, inflation_radius)

    # A* search
    DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    DIAG_COST = math.sqrt(2)

    open_set = [(0.0, sx, sy)]
    g_score = {(sx, sy): 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    closed = set()

    while open_set:
        _, cx, cy = heapq.heappop(open_set)

        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))

        if cx == gx and cy == gy:
            return _reconstruct(came_from, (gx, gy))

        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            if (nx, ny) in closed:
                continue
            if cost_grid[ny][nx] >= 255:  # impassable
                continue

            move_cost = DIAG_COST if (dx != 0 and dy != 0) else 1.0
            cell_cost = cost_grid[ny][nx] / 50.0  # normalize inflation cost
            tentative = g_score[(cx, cy)] + move_cost + cell_cost

            if tentative < g_score.get((nx, ny), float("inf")):
                g_score[(nx, ny)] = tentative
                f = tentative + _heuristic(nx, ny, gx, gy)
                came_from[(nx, ny)] = (cx, cy)
                heapq.heappush(open_set, (f, nx, ny))

    return []  # No path found


def _heuristic(x1: int, y1: int, x2: int, y2: int) -> float:
    """Octile distance heuristic (consistent for 8-directional movement)."""
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


def _build_cost_grid(
    grid: list[list[int]], width: int, height: int, inflation_radius: int
) -> list[list[int]]:
    """Build cost grid with inflation around obstacles (mimics Nav2 InflationLayer)."""
    cost = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if grid[y][x] == 1:
                cost[y][x] = 255  # lethal
                # Inflate surrounding cells
                for dy in range(-inflation_radius, inflation_radius + 1):
                    for dx in range(-inflation_radius, inflation_radius + 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height and cost[ny][nx] < 255:
                            dist = math.sqrt(dx * dx + dy * dy)
                            if dist <= inflation_radius:
                                inflation_cost = int(200 * (1.0 - dist / (inflation_radius + 1)))
                                cost[ny][nx] = max(cost[ny][nx], inflation_cost)
    return cost


def _clamp(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    return max(0, min(x, w - 1)), max(0, min(y, h - 1))


def _find_nearest_free(
    grid: list[list[int]], x: int, y: int, w: int, h: int
) -> tuple[int, int]:
    """Find nearest free cell if start/goal is inside an obstacle."""
    for r in range(1, max(w, h)):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == 0:
                    return nx, ny
    return x, y


def _reconstruct(
    came_from: dict[tuple[int, int], tuple[int, int]], current: tuple[int, int]
) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path
