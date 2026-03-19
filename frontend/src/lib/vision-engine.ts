/**
 * Client-side vision algorithms for browser camera testing.
 * No backend required — runs entirely in the browser.
 *
 * Algorithms:
 *  1. QR Detection (jsQR)
 *  2. Monocular Distance Estimation (pinhole model)
 *  3. Motion Detection (frame differencing)
 *  4. Zone Classification (danger / warning / safe)
 */

import jsQR from "jsqr";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface QRDetection {
  data: string;
  corners: { x: number; y: number }[];
  pixelSize: number;
  distanceCm: number;
  angleDeg: number;
}

export interface DetectedObject {
  className: string;
  score: number;
  bbox: [number, number, number, number]; // [x, y, width, height]
  distanceCm: number;
  zone: "danger" | "warning" | "safe";
}

export interface MotionCell {
  x: number;
  y: number;
  w: number;
  h: number;
  intensity: number;
}

export interface FrameDebug {
  timestamp: number;
  processingMs: number;
  qr: QRDetection | null;
  objects: DetectedObject[];
  motionCells: MotionCell[];
  motionLevel: number;
}

/* ------------------------------------------------------------------ */
/*  1. QR Code Detection                                               */
/* ------------------------------------------------------------------ */

export function scanQR(imageData: ImageData): QRDetection | null {
  const code = jsQR(imageData.data, imageData.width, imageData.height, {
    inversionAttempts: "dontInvert",
  });
  if (!code) return null;

  const loc = code.location;
  const corners = [
    loc.topLeftCorner,
    loc.topRightCorner,
    loc.bottomRightCorner,
    loc.bottomLeftCorner,
  ];

  // QR pixel size (average of width & height in pixels)
  const w = _dist(loc.topLeftCorner, loc.topRightCorner);
  const h = _dist(loc.topLeftCorner, loc.bottomLeftCorner);
  const pixelSize = (w + h) / 2;

  // Distance estimation — assuming real QR code ~5 cm, webcam focal ≈ 600 px
  const QR_REAL_CM = 5;
  const FOCAL_PX = 600;
  const distanceCm = pixelSize > 0 ? (QR_REAL_CM * FOCAL_PX) / pixelSize : 999;

  // Horizontal angle from frame center (rough ±30° mapping)
  const cx = corners.reduce((s, c) => s + c.x, 0) / 4;
  const halfW = imageData.width / 2;
  const angleDeg = halfW > 0 ? ((cx - halfW) / halfW) * 30 : 0;

  return { data: code.data, corners, pixelSize, distanceCm, angleDeg };
}

function _dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

/* ------------------------------------------------------------------ */
/*  2. Monocular Distance Estimation                                   */
/* ------------------------------------------------------------------ */

/** Reference heights (cm) for common COCO-SSD classes */
const REF_HEIGHTS: Record<string, number> = {
  person: 170,
  bicycle: 100,
  car: 150,
  motorcycle: 110,
  bus: 300,
  truck: 250,
  cat: 25,
  dog: 50,
  chair: 80,
  couch: 80,
  bottle: 25,
  cup: 10,
  bowl: 10,
  "cell phone": 14,
  laptop: 25,
  tv: 50,
  book: 25,
  "potted plant": 40,
  backpack: 50,
  umbrella: 90,
  handbag: 30,
  suitcase: 60,
  keyboard: 15,
  mouse: 5,
  scissors: 15,
  "teddy bear": 30,
  clock: 25,
};

/**
 * Pinhole-model distance estimation:
 *   distance = (realHeight × focalLength) / pixelHeight
 */
export function estimateDistance(
  bboxHeight: number,
  frameHeight: number,
  className: string,
): number {
  const refCm = REF_HEIGHTS[className] ?? 50;
  const FOCAL = 600;
  if (bboxHeight <= 0) return 9999;
  // Normalize to 480p reference frame
  const normalized = bboxHeight * (480 / frameHeight);
  return (refCm * FOCAL) / normalized;
}

/* ------------------------------------------------------------------ */
/*  3. Zone Classification                                             */
/* ------------------------------------------------------------------ */

export function classifyZone(distanceCm: number): "danger" | "warning" | "safe" {
  if (distanceCm < 50) return "danger";
  if (distanceCm < 150) return "warning";
  return "safe";
}

export const ZONE_COLORS = {
  danger: { fill: "rgba(239,68,68,0.35)", stroke: "#ef4444", label: "위험" },
  warning: { fill: "rgba(245,158,11,0.25)", stroke: "#f59e0b", label: "주의" },
  safe: { fill: "rgba(34,197,94,0.15)", stroke: "#22c55e", label: "안전" },
} as const;

/* ------------------------------------------------------------------ */
/*  4. Motion Detection (frame differencing)                           */
/* ------------------------------------------------------------------ */

export function detectMotion(
  prevData: Uint8ClampedArray,
  currData: Uint8ClampedArray,
  width: number,
  height: number,
  threshold = 30,
  gridSize = 20,
): { cells: MotionCell[]; level: number } {
  const gw = Math.ceil(width / gridSize);
  const gh = Math.ceil(height / gridSize);
  const counts = new Float32Array(gw * gh);

  let totalDiff = 0;
  const len = width * height;

  for (let i = 0; i < len; i++) {
    const p = i * 4;
    const d =
      Math.abs(currData[p] - prevData[p]) +
      Math.abs(currData[p + 1] - prevData[p + 1]) +
      Math.abs(currData[p + 2] - prevData[p + 2]);
    const avg = d / 3;
    if (avg > threshold) {
      const x = i % width;
      const y = Math.floor(i / width);
      const gx = Math.min(Math.floor(x / gridSize), gw - 1);
      const gy = Math.min(Math.floor(y / gridSize), gh - 1);
      counts[gy * gw + gx]++;
      totalDiff += avg;
    }
  }

  const cellArea = gridSize * gridSize;
  const cells: MotionCell[] = [];

  for (let gy = 0; gy < gh; gy++) {
    for (let gx = 0; gx < gw; gx++) {
      const intensity = counts[gy * gw + gx] / cellArea;
      if (intensity > 0.08) {
        cells.push({
          x: gx * gridSize,
          y: gy * gridSize,
          w: gridSize,
          h: gridSize,
          intensity: Math.min(intensity, 1),
        });
      }
    }
  }

  const level = len > 0 ? totalDiff / (len * 255) : 0;
  return { cells, level };
}
