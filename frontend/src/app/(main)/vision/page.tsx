"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import {
  scanQR,
  estimateDistance,
  classifyZone,
  detectMotion,
  ZONE_COLORS,
  type QRDetection,
  type DetectedObject,
  type MotionCell,
} from "@/lib/vision-engine";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Mode = "qr" | "object" | "obstacle" | "hybrid" | "servoing";

interface LogEntry {
  time: string;
  type: "qr" | "obj" | "motion" | "info" | "error";
  msg: string;
}

/* eslint-disable @typescript-eslint/no-explicit-any */

/* ------------------------------------------------------------------ */
/*  Page Component                                                     */
/* ------------------------------------------------------------------ */

export default function VisionPage() {
  /* ---- refs ---- */
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const runningRef = useRef(false);
  const modelRef = useRef<any>(null);
  const prevFrameRef = useRef<Uint8ClampedArray | null>(null);

  /* ---- camera ---- */
  const [cameraActive, setCameraActive] = useState(false);
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [selectedCamera, setSelectedCamera] = useState("");

  /* ---- mode ---- */
  const [mode, setMode] = useState<Mode>("hybrid");

  /* ---- detection results ---- */
  const [qrResult, setQrResult] = useState<QRDetection | null>(null);
  const [objects, setObjects] = useState<DetectedObject[]>([]);
  const [motionCells, setMotionCells] = useState<MotionCell[]>([]);
  const [motionLevel, setMotionLevel] = useState(0);

  /* ---- servoing ---- */
  const [servoScore, setServoScore] = useState(0);
  const [servoOffsetX, setServoOffsetX] = useState(0);
  const [servoOffsetY, setServoOffsetY] = useState(0);
  const [servoDistanceCm, setServoDistanceCm] = useState(0);

  /* ---- debug ---- */
  const [fps, setFps] = useState(0);
  const [procMs, setProcMs] = useState(0);
  const [modelStatus, setModelStatus] = useState<"unloaded" | "loading" | "ready" | "error">("unloaded");
  const [showDebug, setShowDebug] = useState(true);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [confidence, setConfidence] = useState(0.5);
  const [motionThreshold, setMotionThreshold] = useState(30);

  /* ---- QR generator ---- */
  const [qrGenCode, setQrGenCode] = useState("101동-01");
  const [qrGenType, setQrGenType] = useState("food_waste");
  const [qrImageUrl, setQrImageUrl] = useState<string | null>(null);

  /* ---------------------------------------------------------------- */
  /*  Logging                                                          */
  /* ---------------------------------------------------------------- */

  const addLog = useCallback((type: LogEntry["type"], msg: string) => {
    const time = new Date().toLocaleTimeString("ko-KR", { hour12: false, fractionalSecondDigits: 3 });
    setLogs((prev) => [{ time, type, msg }, ...prev].slice(0, 80));
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Camera                                                           */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    navigator.mediaDevices?.enumerateDevices().then((devs) => {
      const videoDevs = devs.filter((d) => d.kind === "videoinput");
      setCameras(videoDevs);
      if (videoDevs.length > 0 && !selectedCamera) setSelectedCamera(videoDevs[0].deviceId);
    });
  }, [selectedCamera]);

  const startCamera = async () => {
    try {
      const constraints: MediaStreamConstraints = {
        video: selectedCamera
          ? { deviceId: { exact: selectedCamera }, width: { ideal: 640 }, height: { ideal: 480 } }
          : { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 } },
      };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setCameraActive(true);
        addLog("info", "카메라 시작됨");
      }
    } catch (err: any) {
      addLog("error", `카메라 오류: ${err.message}`);
    }
  };

  const stopCamera = () => {
    runningRef.current = false;
    const stream = videoRef.current?.srcObject as MediaStream;
    stream?.getTracks().forEach((t) => t.stop());
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
    setObjects([]);
    setQrResult(null);
    setMotionCells([]);
    setMotionLevel(0);
    prevFrameRef.current = null;
    addLog("info", "카메라 중지됨");
  };

  /* ---------------------------------------------------------------- */
  /*  COCO-SSD Model Loading (dynamic import)                          */
  /* ---------------------------------------------------------------- */

  const loadModel = useCallback(async () => {
    if (modelRef.current || modelStatus === "loading") return;
    setModelStatus("loading");
    addLog("info", "COCO-SSD 모델 로딩 중...");
    try {
      await import("@tensorflow/tfjs");
      const cocoSsd = await import("@tensorflow-models/coco-ssd");
      const model = await cocoSsd.load({ base: "lite_mobilenet_v2" });
      modelRef.current = model;
      setModelStatus("ready");
      addLog("info", "COCO-SSD 모델 로딩 완료 (lite_mobilenet_v2)");
    } catch (err: any) {
      setModelStatus("error");
      addLog("error", `모델 로딩 실패: ${err.message}`);
    }
  }, [modelStatus, addLog]);

  // Auto-load model when object/obstacle/hybrid mode selected
  useEffect(() => {
    if ((mode === "object" || mode === "obstacle" || mode === "hybrid") && modelStatus === "unloaded") {
      loadModel();
    }
  }, [mode, modelStatus, loadModel]);

  /* ---------------------------------------------------------------- */
  /*  Overlay Drawing                                                  */
  /* ---------------------------------------------------------------- */

  const drawOverlay = useCallback(
    (
      qr: QRDetection | null,
      objs: DetectedObject[],
      motCells: MotionCell[],
      frameW: number,
      frameH: number,
    ) => {
      const overlay = overlayRef.current;
      if (!overlay) return;
      overlay.width = frameW;
      overlay.height = frameH;
      const ctx = overlay.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, frameW, frameH);

      // -- Servoing mode overlay --
      if (mode === "servoing") {
        const centerX = frameW / 2;
        const centerY = frameH / 2;

        // 1. Crosshair at frame center
        ctx.strokeStyle = "rgba(255,255,255,0.6)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(centerX, 0);
        ctx.lineTo(centerX, frameH);
        ctx.moveTo(0, centerY);
        ctx.lineTo(frameW, centerY);
        ctx.stroke();

        // Small center target circle
        ctx.strokeStyle = "rgba(255,255,255,0.8)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 15, 0, Math.PI * 2);
        ctx.stroke();

        if (qr) {
          // QR center
          const qrCx = qr.corners.reduce((s, c) => s + c.x, 0) / 4;
          const qrCy = qr.corners.reduce((s, c) => s + c.y, 0) / 4;

          // Green box around QR code
          ctx.strokeStyle = "#22c55e";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(qr.corners[0].x, qr.corners[0].y);
          for (let i = 1; i < qr.corners.length; i++) {
            ctx.lineTo(qr.corners[i].x, qr.corners[i].y);
          }
          ctx.closePath();
          ctx.stroke();
          ctx.fillStyle = "rgba(34,197,94,0.15)";
          ctx.fill();

          // Arrow from QR center to frame center
          const dx = centerX - qrCx;
          const dy = centerY - qrCy;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist > 10) {
            const angle = Math.atan2(dy, dx);
            const arrowLen = Math.min(dist, 80);
            const arrowEndX = qrCx + Math.cos(angle) * arrowLen;
            const arrowEndY = qrCy + Math.sin(angle) * arrowLen;

            ctx.strokeStyle = "#fbbf24";
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.moveTo(qrCx, qrCy);
            ctx.lineTo(arrowEndX, arrowEndY);
            ctx.stroke();

            // Arrowhead
            const headLen = 12;
            ctx.fillStyle = "#fbbf24";
            ctx.beginPath();
            ctx.moveTo(arrowEndX, arrowEndY);
            ctx.lineTo(
              arrowEndX - headLen * Math.cos(angle - 0.4),
              arrowEndY - headLen * Math.sin(angle - 0.4),
            );
            ctx.lineTo(
              arrowEndX - headLen * Math.cos(angle + 0.4),
              arrowEndY - headLen * Math.sin(angle + 0.4),
            );
            ctx.closePath();
            ctx.fill();
          }

          // Offset text
          const offsetX = Math.round(qrCx - centerX);
          const offsetY = Math.round(qrCy - centerY);
          const offsetStr = `X: ${offsetX >= 0 ? "+" : ""}${offsetX}px, Y: ${offsetY >= 0 ? "+" : ""}${offsetY}px`;
          ctx.fillStyle = "rgba(0,0,0,0.75)";
          const otw = ctx.measureText(offsetStr).width + 12;
          ctx.fillRect(centerX - otw / 2, frameH - 40, otw, 22);
          ctx.fillStyle = "#fff";
          ctx.font = "bold 12px monospace";
          ctx.textAlign = "center";
          ctx.fillText(offsetStr, centerX, frameH - 24);
          ctx.textAlign = "start";

          // Alignment score calculation
          const maxOffset = Math.sqrt(centerX * centerX + centerY * centerY);
          const centerOffsetPercent = (dist / maxOffset) * 100;
          const optimalDist = 30; // cm
          const distanceErrorPercent = Math.min(Math.abs(qr.distanceCm - optimalDist) / optimalDist * 100, 100);
          const score = Math.max(0, Math.min(100, 100 - (centerOffsetPercent * 0.7 + distanceErrorPercent * 0.3)));

          // Alignment score display (large number)
          const scoreColor = score > 80 ? "#22c55e" : score > 50 ? "#fbbf24" : "#ef4444";
          ctx.fillStyle = "rgba(0,0,0,0.7)";
          ctx.fillRect(frameW - 110, 10, 100, 60);
          ctx.fillStyle = scoreColor;
          ctx.font = "bold 36px monospace";
          ctx.textAlign = "center";
          ctx.fillText(`${Math.round(score)}`, frameW - 60, 50);
          ctx.fillStyle = "rgba(255,255,255,0.7)";
          ctx.font = "10px sans-serif";
          ctx.fillText("정렬 점수", frameW - 60, 64);
          ctx.textAlign = "start";

          // Distance guide bar
          const barX = 10;
          const barY = frameH - 70;
          const barW = frameW - 20;
          const barH = 16;

          // Bar background
          ctx.fillStyle = "rgba(0,0,0,0.5)";
          ctx.fillRect(barX, barY - 18, barW, barH + 20);

          // Three zones on bar: red (<20cm) | green (20-40cm) | yellow (>40cm)
          const zoneWidth = barW / 3;
          ctx.fillStyle = "rgba(239,68,68,0.6)";
          ctx.fillRect(barX, barY, zoneWidth, barH);
          ctx.fillStyle = "rgba(34,197,94,0.6)";
          ctx.fillRect(barX + zoneWidth, barY, zoneWidth, barH);
          ctx.fillStyle = "rgba(245,158,11,0.6)";
          ctx.fillRect(barX + zoneWidth * 2, barY, zoneWidth, barH);

          // Distance indicator position
          const clampedDist = Math.max(0, Math.min(60, qr.distanceCm));
          const indicatorX = barX + (clampedDist / 60) * barW;
          ctx.fillStyle = "#fff";
          ctx.beginPath();
          ctx.moveTo(indicatorX, barY - 4);
          ctx.lineTo(indicatorX - 5, barY - 12);
          ctx.lineTo(indicatorX + 5, barY - 12);
          ctx.closePath();
          ctx.fill();
          ctx.fillRect(indicatorX - 1.5, barY, 3, barH);

          // Distance zone labels
          ctx.font = "bold 9px sans-serif";
          ctx.textAlign = "center";
          ctx.fillStyle = "#fca5a5";
          ctx.fillText("너무 가까움 (<20cm)", barX + zoneWidth / 2, barY + barH + 12);
          ctx.fillStyle = "#86efac";
          ctx.fillText("적정 거리 (20-40cm)", barX + zoneWidth * 1.5, barY + barH + 12);
          ctx.fillStyle = "#fde68a";
          ctx.fillText("너무 멂 (>40cm)", barX + zoneWidth * 2.5, barY + barH + 12);
          ctx.textAlign = "start";

          // Distance text
          let distLabel: string;
          let distColor: string;
          if (qr.distanceCm < 20) {
            distLabel = `너무 가까움 (${qr.distanceCm.toFixed(0)}cm)`;
            distColor = "#ef4444";
          } else if (qr.distanceCm <= 40) {
            distLabel = `적정 거리 (${qr.distanceCm.toFixed(0)}cm)`;
            distColor = "#22c55e";
          } else {
            distLabel = `너무 멂 (${qr.distanceCm.toFixed(0)}cm)`;
            distColor = "#fbbf24";
          }
          ctx.fillStyle = "rgba(0,0,0,0.7)";
          const dtw = ctx.measureText(distLabel).width + 12;
          ctx.fillRect(10, 10, dtw, 22);
          ctx.fillStyle = distColor;
          ctx.font = "bold 12px sans-serif";
          ctx.fillText(distLabel, 16, 26);

          // Direction arrows on edges
          const arrowSize = 30;
          ctx.font = `bold ${arrowSize}px sans-serif`;
          ctx.textAlign = "center";

          // Horizontal arrows (left/right)
          if (offsetX > 15) {
            // QR is right of center -> robot should move right
            ctx.fillStyle = "rgba(251,191,36,0.8)";
            ctx.fillText("\u2192", frameW - 30, centerY);
          } else if (offsetX < -15) {
            // QR is left of center -> robot should move left
            ctx.fillStyle = "rgba(251,191,36,0.8)";
            ctx.fillText("\u2190", 30, centerY);
          }

          // Vertical arrows (forward/back based on distance)
          if (qr.distanceCm > 40) {
            // Too far -> move forward (up arrow)
            ctx.fillStyle = "rgba(251,191,36,0.8)";
            ctx.fillText("\u2191", centerX, 35);
          } else if (qr.distanceCm < 20) {
            // Too close -> move back (down arrow)
            ctx.fillStyle = "rgba(251,191,36,0.8)";
            ctx.fillText("\u2193", centerX, frameH - 85);
          }

          ctx.textAlign = "start";

          // "Alignment complete!" overlay
          if (score > 90) {
            ctx.fillStyle = "rgba(34,197,94,0.2)";
            ctx.fillRect(0, 0, frameW, frameH);
            ctx.fillStyle = "#22c55e";
            ctx.font = "bold 28px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("\uc815\ub82c \uc644\ub8cc!", centerX, centerY - 40);
            ctx.textAlign = "start";
          }
        } else {
          // No QR detected — show "searching" message
          ctx.fillStyle = "rgba(0,0,0,0.6)";
          ctx.fillRect(frameW / 2 - 100, frameH / 2 - 15, 200, 30);
          ctx.fillStyle = "rgba(255,255,255,0.8)";
          ctx.font = "14px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText("QR \ucf54\ub4dc\ub97c \ucc3e\ub294 \uc911...", frameW / 2, frameH / 2 + 5);
          ctx.textAlign = "start";
        }

        return; // servoing mode has its own complete overlay, skip other modes' drawing
      }

      // -- QR overlay --
      if (qr) {
        ctx.strokeStyle = "#a855f7";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(qr.corners[0].x, qr.corners[0].y);
        for (let i = 1; i < qr.corners.length; i++) {
          ctx.lineTo(qr.corners[i].x, qr.corners[i].y);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.fillStyle = "rgba(168,85,247,0.15)";
        ctx.fill();

        // QR info label
        const lx = qr.corners[0].x;
        const ly = qr.corners[0].y - 8;
        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.fillRect(lx, ly - 16, 220, 20);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 12px monospace";
        ctx.fillText(
          `QR: ${qr.data.slice(0, 25)} | ${qr.distanceCm.toFixed(0)}cm | ${qr.angleDeg.toFixed(1)}°`,
          lx + 4,
          ly - 2,
        );
      }

      // -- Object detection boxes --
      for (const obj of objs) {
        const [x, y, w, h] = obj.bbox;
        const zc = ZONE_COLORS[obj.zone];
        ctx.strokeStyle = zc.stroke;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.fillStyle = zc.fill;
        ctx.fillRect(x, y, w, h);

        // Label
        const label = `${obj.className} ${(obj.score * 100).toFixed(0)}% ${obj.distanceCm.toFixed(0)}cm [${zc.label}]`;
        ctx.fillStyle = "rgba(0,0,0,0.75)";
        const tw = ctx.measureText(label).width + 8;
        ctx.fillRect(x, y - 18, tw, 18);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 11px monospace";
        ctx.fillText(label, x + 4, y - 4);
      }

      // -- Motion cells --
      for (const cell of motCells) {
        const alpha = Math.min(cell.intensity * 0.6, 0.5);
        ctx.fillStyle = `rgba(255, 100, 0, ${alpha})`;
        ctx.fillRect(cell.x, cell.y, cell.w, cell.h);
        ctx.strokeStyle = `rgba(255, 100, 0, ${alpha + 0.2})`;
        ctx.lineWidth = 1;
        ctx.strokeRect(cell.x, cell.y, cell.w, cell.h);
      }

      // -- Obstacle zone bands (bottom = near, top = far) --
      if (mode === "obstacle" || mode === "hybrid") {
        const bandH = frameH / 3;
        // Bottom third: danger
        ctx.fillStyle = "rgba(239,68,68,0.08)";
        ctx.fillRect(0, frameH - bandH, frameW, bandH);
        // Middle third: warning
        ctx.fillStyle = "rgba(245,158,11,0.06)";
        ctx.fillRect(0, frameH - bandH * 2, frameW, bandH);
        // Top third: safe
        ctx.fillStyle = "rgba(34,197,94,0.04)";
        ctx.fillRect(0, 0, frameW, bandH);

        // Labels
        ctx.font = "bold 10px sans-serif";
        ctx.fillStyle = "rgba(239,68,68,0.5)";
        ctx.fillText("\uc704\ud5d8 (<50cm)", 4, frameH - 6);
        ctx.fillStyle = "rgba(245,158,11,0.5)";
        ctx.fillText("\uc8fc\uc758 (50-150cm)", 4, frameH - bandH - 6);
        ctx.fillStyle = "rgba(34,197,94,0.5)";
        ctx.fillText("\uc548\uc804 (>150cm)", 4, bandH - 6);
      }
    },
    [mode],
  );

  /* ---------------------------------------------------------------- */
  /*  Detection Loop                                                   */
  /* ---------------------------------------------------------------- */

  const runLoop = useCallback(async () => {
    runningRef.current = true;
    let frameCount = 0;
    let fpsTime = performance.now();

    const step = async () => {
      if (!runningRef.current) return;

      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.videoWidth === 0) {
        requestAnimationFrame(step);
        return;
      }

      const t0 = performance.now();
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(video, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const currentMode = mode;

      let qr: QRDetection | null = null;
      let objs: DetectedObject[] = [];
      let motCells: MotionCell[] = [];
      let motLvl = 0;

      // --- QR detection ---
      if (currentMode === "qr" || currentMode === "hybrid" || currentMode === "servoing") {
        qr = scanQR(imageData);
        if (qr) {
          addLog("qr", `${qr.data.slice(0, 30)} | 거리: ${qr.distanceCm.toFixed(1)}cm | 각도: ${qr.angleDeg.toFixed(1)}°`);
        }
      }

      // --- Servoing state update ---
      if (currentMode === "servoing") {
        if (qr) {
          const frameCenterX = canvas.width / 2;
          const frameCenterY = canvas.height / 2;
          const qrCx = qr.corners.reduce((s, c) => s + c.x, 0) / 4;
          const qrCy = qr.corners.reduce((s, c) => s + c.y, 0) / 4;
          const offX = Math.round(qrCx - frameCenterX);
          const offY = Math.round(qrCy - frameCenterY);
          const maxOffset = Math.sqrt(frameCenterX ** 2 + frameCenterY ** 2);
          const centerDist = Math.sqrt(offX ** 2 + offY ** 2);
          const centerOffsetPct = (centerDist / maxOffset) * 100;
          const optimalDist = 30;
          const distErrPct = Math.min(Math.abs(qr.distanceCm - optimalDist) / optimalDist * 100, 100);
          const score = Math.max(0, Math.min(100, 100 - (centerOffsetPct * 0.7 + distErrPct * 0.3)));
          setServoScore(Math.round(score));
          setServoOffsetX(offX);
          setServoOffsetY(offY);
          setServoDistanceCm(qr.distanceCm);
          if (score > 90) {
            addLog("info", `서보잉 정렬 완료! 점수: ${Math.round(score)}%`);
          }
        } else {
          setServoScore(0);
          setServoOffsetX(0);
          setServoOffsetY(0);
          setServoDistanceCm(0);
        }
      }

      // --- Object detection (COCO-SSD) ---
      if ((currentMode === "object" || currentMode === "obstacle" || currentMode === "hybrid") && modelRef.current) {
        try {
          const predictions = await modelRef.current.detect(canvas);
          objs = predictions
            .filter((p: any) => p.score >= confidence)
            .map((p: any) => {
              const dist = estimateDistance(p.bbox[3], canvas.height, p.class);
              return {
                className: p.class,
                score: p.score,
                bbox: p.bbox as [number, number, number, number],
                distanceCm: dist,
                zone: classifyZone(dist),
              };
            });

          for (const obj of objs) {
            addLog("obj", `${obj.className} ${(obj.score * 100).toFixed(0)}% | ${obj.distanceCm.toFixed(0)}cm [${ZONE_COLORS[obj.zone].label}]`);
          }
        } catch (err: any) {
          addLog("error", `감지 오류: ${err.message}`);
        }
      }

      // --- Motion detection ---
      if (currentMode === "obstacle" || currentMode === "hybrid") {
        if (prevFrameRef.current) {
          const mot = detectMotion(
            prevFrameRef.current,
            imageData.data,
            canvas.width,
            canvas.height,
            motionThreshold,
          );
          motCells = mot.cells;
          motLvl = mot.level;
          if (motLvl > 0.02) {
            addLog("motion", `움직임 ${(motLvl * 100).toFixed(1)}% | ${motCells.length}셀`);
          }
        }
        prevFrameRef.current = new Uint8ClampedArray(imageData.data);
      }

      // --- Update state ---
      setQrResult(qr);
      setObjects(objs);
      setMotionCells(motCells);
      setMotionLevel(motLvl);

      // --- Draw overlay ---
      drawOverlay(qr, objs, motCells, canvas.width, canvas.height);

      // --- FPS ---
      const t1 = performance.now();
      setProcMs(t1 - t0);
      frameCount++;
      if (t1 - fpsTime >= 1000) {
        setFps(frameCount);
        frameCount = 0;
        fpsTime = t1;
      }

      // Throttle: wait a bit before next frame (target ~12 FPS for detection)
      setTimeout(() => requestAnimationFrame(step), 80);
    };

    requestAnimationFrame(step);
  }, [mode, confidence, motionThreshold, addLog, drawOverlay]);

  useEffect(() => {
    if (cameraActive) {
      runLoop();
    }
    return () => {
      runningRef.current = false;
    };
  }, [cameraActive, runLoop]);

  /* ---------------------------------------------------------------- */
  /*  QR Generator (client-side)                                       */
  /* ---------------------------------------------------------------- */

  const handleGenerateQR = async () => {
    try {
      const QRCode = (await import("qrcode")).default;
      const data = JSON.stringify({
        bin_code: qrGenCode,
        bin_type: qrGenType,
        capacity: "3L",
      });
      const url = await QRCode.toDataURL(data, { width: 256, margin: 2 });
      setQrImageUrl(url);
      addLog("info", `QR 생성: ${qrGenCode}`);
    } catch (err: any) {
      addLog("error", `QR 생성 실패: ${err.message}`);
    }
  };

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  const logColor: Record<LogEntry["type"], string> = {
    qr: "text-purple-400",
    obj: "text-blue-400",
    motion: "text-orange-400",
    info: "text-green-400",
    error: "text-red-400",
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">비전 테스트</h1>
        <p className="text-gray-500 mt-1">
          브라우저 카메라로 QR 인식, 물체 탐지, 장애물 감지, Visual Servoing 알고리즘을 테스트합니다 (백엔드 불필요)
        </p>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-3 flex flex-wrap items-center gap-3">
        {/* Camera toggle */}
        {!cameraActive ? (
          <button onClick={startCamera} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
            카메라 시작
          </button>
        ) : (
          <button onClick={stopCamera} className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700">
            카메라 중지
          </button>
        )}

        {/* Camera selector */}
        {cameras.length > 1 && (
          <select
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700"
          >
            {cameras.map((c) => (
              <option key={c.deviceId} value={c.deviceId}>
                {c.label || `카메라 ${cameras.indexOf(c) + 1}`}
              </option>
            ))}
          </select>
        )}

        {/* Mode tabs */}
        <div className="flex bg-gray-100 rounded-lg p-0.5 ml-auto">
          {([
            ["qr", "QR"],
            ["object", "물체감지"],
            ["obstacle", "장애물"],
            ["hybrid", "하이브리드"],
            ["servoing", "서보잉"],
          ] as [Mode, string][]).map(([m, label]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                mode === m ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Debug toggle */}
        <button
          onClick={() => setShowDebug((v) => !v)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium border ${
            showDebug ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-600 border-gray-300"
          }`}
        >
          디버그
        </button>
      </div>

      {/* Main Area */}
      <div className="flex gap-4">
        {/* Left: Camera + Results */}
        <div className="flex-1 space-y-4">
          {/* Camera view */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-3">
            <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: "4/3" }}>
              <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
              <canvas ref={overlayRef} className="absolute inset-0 w-full h-full" />
              {!cameraActive && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 gap-2">
                  <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span className="text-sm">카메라를 시작하세요</span>
                </div>
              )}
              {cameraActive && (
                <div className="absolute top-2 right-2 flex gap-2">
                  <span className="bg-black/60 text-white px-2 py-1 rounded text-xs font-mono">
                    {fps} FPS
                  </span>
                  <span className="bg-black/60 text-white px-2 py-1 rounded text-xs font-mono">
                    {procMs.toFixed(0)}ms
                  </span>
                  {modelStatus === "loading" && (
                    <span className="bg-yellow-500/80 text-white px-2 py-1 rounded text-xs animate-pulse">
                      모델 로딩중...
                    </span>
                  )}
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />
          </div>

          {/* Servoing Results Panel */}
          {mode === "servoing" && cameraActive && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-3">Visual Servoing</h3>
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center">
                  <div className={`text-3xl font-bold font-mono ${
                    servoScore > 80 ? "text-green-600" : servoScore > 50 ? "text-yellow-500" : "text-red-500"
                  }`}>
                    {servoScore}%
                  </div>
                  <div className="text-xs text-gray-500 mt-1">정렬 점수</div>
                </div>
                <div className="text-center">
                  <div className="text-sm font-mono text-gray-900">
                    <div>X: {servoOffsetX >= 0 ? "+" : ""}{servoOffsetX}px</div>
                    <div>Y: {servoOffsetY >= 0 ? "+" : ""}{servoOffsetY}px</div>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">오프셋</div>
                </div>
                <div className="text-center">
                  <div className={`text-lg font-bold font-mono ${
                    servoDistanceCm > 0 && servoDistanceCm >= 20 && servoDistanceCm <= 40
                      ? "text-green-600"
                      : servoDistanceCm > 40
                      ? "text-yellow-500"
                      : servoDistanceCm > 0
                      ? "text-red-500"
                      : "text-gray-400"
                  }`}>
                    {servoDistanceCm > 0 ? `${servoDistanceCm.toFixed(0)}cm` : "--"}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">거리</div>
                </div>
              </div>
              {servoScore > 90 && (
                <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-2 text-center">
                  <span className="text-green-700 font-semibold text-sm">정렬 완료! 수거 가능</span>
                </div>
              )}
            </div>
          )}

          {/* Detection Results */}
          {(objects.length > 0 || qrResult) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-3">감지 결과</h3>

              {/* QR result */}
              {qrResult && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mb-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 bg-purple-500 rounded-full" />
                    <span className="font-medium text-purple-900 text-sm">QR 코드 감지</span>
                  </div>
                  <p className="text-sm text-purple-800 font-mono">{qrResult.data}</p>
                  <div className="flex gap-4 mt-1 text-xs text-purple-600">
                    <span>거리: {qrResult.distanceCm.toFixed(1)}cm</span>
                    <span>각도: {qrResult.angleDeg.toFixed(1)}&deg;</span>
                    <span>크기: {qrResult.pixelSize.toFixed(0)}px</span>
                  </div>
                </div>
              )}

              {/* Object results */}
              {objects.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {objects.map((obj, i) => {
                    const zc = ZONE_COLORS[obj.zone];
                    return (
                      <div
                        key={i}
                        className="rounded-lg p-2 text-sm border"
                        style={{ borderColor: zc.stroke, backgroundColor: zc.fill }}
                      >
                        <div className="flex justify-between items-center">
                          <span className="font-medium text-gray-900">{obj.className}</span>
                          <span className="text-xs font-mono" style={{ color: zc.stroke }}>
                            {zc.label}
                          </span>
                        </div>
                        <div className="text-xs text-gray-600 mt-0.5">
                          {(obj.score * 100).toFixed(0)}% | ~{obj.distanceCm.toFixed(0)}cm
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Motion indicator */}
              {motionLevel > 0.005 && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-600">움직임 감지</span>
                    <span className="font-mono text-orange-600">{(motionLevel * 100).toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-orange-500 h-2 rounded-full transition-all"
                      style={{ width: `${Math.min(motionLevel * 500, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Debug Panel + QR Generator */}
        {showDebug && (
          <div className="w-80 space-y-4">
            {/* Debug Info */}
            <div className="bg-gray-900 rounded-xl p-4 text-sm">
              <h3 className="text-white font-semibold mb-3">디버그 패널</h3>

              {/* Status grid */}
              <div className="grid grid-cols-2 gap-2 mb-4">
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">모델</span>
                  <div className={`font-mono text-sm ${
                    modelStatus === "ready" ? "text-green-400" :
                    modelStatus === "loading" ? "text-yellow-400" :
                    modelStatus === "error" ? "text-red-400" : "text-gray-500"
                  }`}>
                    {modelStatus === "ready" ? "Ready" :
                     modelStatus === "loading" ? "Loading..." :
                     modelStatus === "error" ? "Error" : "Unloaded"}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">FPS</span>
                  <div className="text-white font-mono text-sm">{fps}</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">처리시간</span>
                  <div className="text-white font-mono text-sm">{procMs.toFixed(1)}ms</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">감지 객체</span>
                  <div className="text-white font-mono text-sm">{objects.length}개</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">QR</span>
                  <div className={`font-mono text-sm ${qrResult ? "text-purple-400" : "text-gray-500"}`}>
                    {qrResult ? "감지됨" : "없음"}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-2">
                  <span className="text-gray-400 text-xs">움직임</span>
                  <div className="text-orange-400 font-mono text-sm">
                    {(motionLevel * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Parameter sliders */}
              <div className="space-y-3 mb-4">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">신뢰도 임계값</span>
                    <span className="text-white font-mono">{(confidence * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="95"
                    value={confidence * 100}
                    onChange={(e) => setConfidence(Number(e.target.value) / 100)}
                    className="w-full h-1 bg-gray-700 rounded-full appearance-none cursor-pointer"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">모션 민감도</span>
                    <span className="text-white font-mono">{motionThreshold}</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="80"
                    value={motionThreshold}
                    onChange={(e) => setMotionThreshold(Number(e.target.value))}
                    className="w-full h-1 bg-gray-700 rounded-full appearance-none cursor-pointer"
                  />
                </div>
              </div>

              {/* Algorithm info */}
              <div className="text-xs text-gray-500 space-y-1 border-t border-gray-700 pt-3">
                <p><span className="text-gray-400">QR:</span> jsQR (client-side)</p>
                <p><span className="text-gray-400">물체감지:</span> COCO-SSD (TF.js lite_mobilenet_v2)</p>
                <p><span className="text-gray-400">거리추정:</span> Pinhole model (focal=600px)</p>
                <p><span className="text-gray-400">모션:</span> Frame differencing (grid 20px)</p>
                <p><span className="text-gray-400">존분류:</span> &lt;50cm 위험 / 50-150cm 주의 / &gt;150cm 안전</p>
              </div>
            </div>

            {/* QR Generator */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-3">QR 코드 생성</h3>
              <div className="space-y-2">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">쓰레기통 코드</label>
                  <input
                    type="text"
                    value={qrGenCode}
                    onChange={(e) => setQrGenCode(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">종류</label>
                  <select
                    value={qrGenType}
                    onChange={(e) => setQrGenType(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700"
                  >
                    <option value="food_waste">음식물</option>
                    <option value="general">일반</option>
                    <option value="recyclable">재활용</option>
                  </select>
                </div>
                <button
                  onClick={handleGenerateQR}
                  className="w-full bg-purple-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-purple-700"
                >
                  QR 생성
                </button>
                {qrImageUrl && (
                  <div className="text-center mt-2">
                    <img src={qrImageUrl} alt="QR Code" className="mx-auto border rounded-lg" width={180} />
                    <p className="text-xs text-gray-500 mt-1 font-mono break-all">
                      {JSON.stringify({ bin_code: qrGenCode, bin_type: qrGenType, capacity: "3L" })}
                    </p>
                    <a
                      href={qrImageUrl}
                      download={`qr-${qrGenCode}.png`}
                      className="text-sm text-purple-600 hover:underline mt-1 inline-block"
                    >
                      다운로드
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Detection Log */}
      <div className="bg-gray-900 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-white font-semibold text-sm">감지 로그</h3>
          <button
            onClick={() => setLogs([])}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            초기화
          </button>
        </div>
        <div className="h-40 overflow-y-auto font-mono text-xs space-y-0.5">
          {logs.length === 0 ? (
            <p className="text-gray-600">카메라를 시작하면 감지 로그가 여기에 표시됩니다</p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-gray-600 whitespace-nowrap">{log.time}</span>
                <span className={`${logColor[log.type]} whitespace-nowrap`}>
                  [{log.type.toUpperCase().padEnd(6)}]
                </span>
                <span className="text-gray-300 break-all">{log.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
