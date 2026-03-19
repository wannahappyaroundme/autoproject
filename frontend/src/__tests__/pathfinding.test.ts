import { describe, it, expect } from 'vitest';
import { findPath, MOCK_MAP } from '@/lib/mock-data';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Create a simple grid filled with 0 (open). */
function openGrid(w: number, h: number): number[][] {
  return Array.from({ length: h }, () => Array(w).fill(0));
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe('findPath — A* pathfinding', () => {
  it('finds a path on a fully open grid', () => {
    const grid = openGrid(10, 10);
    const path = findPath(grid, 0, 0, 9, 9);
    expect(path.length).toBeGreaterThan(1);
    expect(path[0]).toEqual([0, 0]);
    expect(path[path.length - 1]).toEqual([9, 9]);
  });

  it('avoids walls (path goes around an obstacle)', () => {
    const grid = openGrid(10, 10);
    // Place a vertical wall at x=5, y=0..8 (leaving y=9 open)
    for (let y = 0; y <= 8; y++) grid[y][5] = 1;

    const path = findPath(grid, 0, 0, 9, 0);
    expect(path.length).toBeGreaterThan(1);
    expect(path[0]).toEqual([0, 0]);
    expect(path[path.length - 1]).toEqual([9, 0]);

    // Path must never step on a wall cell
    for (const [x, y] of path) {
      expect(grid[y][x]).toBe(0);
    }
  });

  it('returns a single point when start === end', () => {
    const grid = openGrid(5, 5);
    const path = findPath(grid, 3, 3, 3, 3);
    expect(path).toEqual([[3, 3]]);
  });

  it('returns fallback straight line when destination is unreachable', () => {
    const grid = openGrid(7, 7);
    // Surround cell (3,3) with walls
    grid[2][3] = 1;
    grid[4][3] = 1;
    grid[3][2] = 1;
    grid[3][4] = 1;

    const path = findPath(grid, 0, 0, 3, 3);
    // Fallback: [[startX, startY], [endX, endY]]
    expect(path).toEqual([[0, 0], [3, 3]]);
  });

  it('never walks through walls', () => {
    const grid = openGrid(15, 15);
    // Scatter some walls
    grid[3][5] = 1;
    grid[3][6] = 1;
    grid[3][7] = 1;
    grid[7][10] = 1;
    grid[8][10] = 1;

    const path = findPath(grid, 0, 0, 14, 14);
    for (const [x, y] of path) {
      expect(grid[y][x]).toBe(0);
    }
  });

  it('moves 4-directionally only (no diagonals)', () => {
    const grid = openGrid(10, 10);
    const path = findPath(grid, 0, 0, 9, 9);

    for (let i = 1; i < path.length; i++) {
      const [x1, y1] = path[i - 1];
      const [x2, y2] = path[i];
      const dx = Math.abs(x2 - x1);
      const dy = Math.abs(y2 - y1);
      // Each step must change exactly one coordinate by 1
      expect(dx + dy).toBe(1);
    }
  });

  it('works on the actual MOCK_MAP grid (collection_point to bin)', () => {
    const { grid, collection_point } = MOCK_MAP;
    const [cpX, cpY] = collection_point;

    // Bin at (7, 8) — "101동-01"
    const path = findPath(grid, cpX, cpY, 7, 8);

    expect(path.length).toBeGreaterThan(1);
    expect(path[0]).toEqual([cpX, cpY]);
    expect(path[path.length - 1]).toEqual([7, 8]);

    // Verify the path never crosses a wall on the real map
    for (const [x, y] of path) {
      expect(grid[y][x]).toBe(0);
    }
  });
});
