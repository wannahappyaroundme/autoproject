import { describe, it, expect } from 'vitest';
import {
  estimateDistance,
  classifyZone,
  detectMotion,
  scanQR,
} from '@/lib/vision-engine';

/* ------------------------------------------------------------------ */
/*  estimateDistance                                                    */
/* ------------------------------------------------------------------ */

describe('estimateDistance — pinhole model', () => {
  it('returns correct distance for a known class and bbox', () => {
    // person: refCm = 170, FOCAL = 600, frameHeight = 480
    // normalized = bboxHeight * (480 / 480) = bboxHeight
    // distance = (170 * 600) / bboxHeight
    const bboxHeight = 240; // half the frame
    const expected = (170 * 600) / 240; // 425 cm
    expect(estimateDistance(bboxHeight, 480, 'person')).toBeCloseTo(expected, 1);
  });

  it('scales correctly for different frame heights', () => {
    // frameHeight = 720: normalized = 360 * (480 / 720) = 240
    const dist = estimateDistance(360, 720, 'person');
    const expected = (170 * 600) / 240; // same as above
    expect(dist).toBeCloseTo(expected, 1);
  });

  it('uses default refCm of 50 for unknown classes', () => {
    const dist = estimateDistance(100, 480, 'unknown_object');
    const expected = (50 * 600) / 100;
    expect(dist).toBeCloseTo(expected, 1);
  });

  it('returns 9999 when bboxHeight is 0', () => {
    expect(estimateDistance(0, 480, 'person')).toBe(9999);
  });

  it('returns 9999 when bboxHeight is negative', () => {
    expect(estimateDistance(-10, 480, 'person')).toBe(9999);
  });
});

/* ------------------------------------------------------------------ */
/*  classifyZone                                                       */
/* ------------------------------------------------------------------ */

describe('classifyZone', () => {
  it('returns "danger" when distance < 50 cm', () => {
    expect(classifyZone(0)).toBe('danger');
    expect(classifyZone(30)).toBe('danger');
    expect(classifyZone(49)).toBe('danger');
  });

  it('returns "warning" when 50 <= distance < 150 cm', () => {
    expect(classifyZone(50)).toBe('warning');
    expect(classifyZone(100)).toBe('warning');
    expect(classifyZone(149)).toBe('warning');
  });

  it('returns "safe" when distance >= 150 cm', () => {
    expect(classifyZone(150)).toBe('safe');
    expect(classifyZone(500)).toBe('safe');
    expect(classifyZone(9999)).toBe('safe');
  });
});

/* ------------------------------------------------------------------ */
/*  detectMotion                                                       */
/* ------------------------------------------------------------------ */

describe('detectMotion', () => {
  const W = 40;
  const H = 40;
  const LEN = W * H * 4;

  /** Create a Uint8ClampedArray filled with a single RGBA value. */
  function solidFrame(r: number, g: number, b: number): Uint8ClampedArray {
    const arr = new Uint8ClampedArray(LEN);
    for (let i = 0; i < W * H; i++) {
      arr[i * 4] = r;
      arr[i * 4 + 1] = g;
      arr[i * 4 + 2] = b;
      arr[i * 4 + 3] = 255;
    }
    return arr;
  }

  it('reports no motion (level 0) for identical frames', () => {
    const frame = solidFrame(100, 100, 100);
    const { cells, level } = detectMotion(frame, frame, W, H);
    expect(level).toBe(0);
    expect(cells).toEqual([]);
  });

  it('detects motion when frames differ significantly', () => {
    const prev = solidFrame(0, 0, 0);
    const curr = solidFrame(200, 200, 200);
    const { level } = detectMotion(prev, curr, W, H);
    expect(level).toBeGreaterThan(0);
  });

  it('returns motion cells for large differences', () => {
    const prev = solidFrame(0, 0, 0);
    const curr = solidFrame(255, 255, 255);
    const { cells } = detectMotion(prev, curr, W, H);
    expect(cells.length).toBeGreaterThan(0);
  });

  it('respects custom threshold', () => {
    const prev = solidFrame(100, 100, 100);
    const curr = solidFrame(110, 110, 110); // diff of 10 per channel
    // Default threshold = 30 → below threshold → no motion
    const { level: lowLevel } = detectMotion(prev, curr, W, H, 30);
    expect(lowLevel).toBe(0);
    // Threshold of 5 → above threshold → detects motion
    const { level: highLevel } = detectMotion(prev, curr, W, H, 5);
    expect(highLevel).toBeGreaterThan(0);
  });
});

/* ------------------------------------------------------------------ */
/*  scanQR                                                             */
/* ------------------------------------------------------------------ */

describe('scanQR', () => {
  it('returns null for a blank (solid white) ImageData', () => {
    const width = 100;
    const height = 100;
    const data = new Uint8ClampedArray(width * height * 4);
    // Fill with white
    for (let i = 0; i < data.length; i += 4) {
      data[i] = 255;
      data[i + 1] = 255;
      data[i + 2] = 255;
      data[i + 3] = 255;
    }
    const imageData = { data, width, height, colorSpace: 'srgb' as const };
    const result = scanQR(imageData as ImageData);
    expect(result).toBeNull();
  });
});
