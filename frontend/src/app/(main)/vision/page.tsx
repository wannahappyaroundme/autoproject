"use client";
import { useRef, useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import type { Detection } from "@/lib/types";

export default function VisionPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [mode, setMode] = useState<"qr" | "yolo" | "hybrid">("qr");
  const [qrResult, setQrResult] = useState<{ data: Record<string, string> | null; distance: number | null; angle: number | null } | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [fps, setFps] = useState(0);
  const [qrGenCode, setQrGenCode] = useState("101동-01");
  const [qrImageUrl, setQrImageUrl] = useState<string | null>(null);
  const runningRef = useRef(false);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setCameraActive(true);
      }
    } catch (err) {
      console.error("Camera error:", err);
    }
  };

  const stopCamera = () => {
    runningRef.current = false;
    const stream = videoRef.current?.srcObject as MediaStream;
    stream?.getTracks().forEach((t) => t.stop());
    setCameraActive(false);
    setDetections([]);
    setQrResult(null);
  };

  const captureFrame = useCallback((): Blob | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return null;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(video, 0, 0);
    let blob: Blob | null = null;
    canvas.toBlob((b) => { blob = b; }, "image/jpeg", 0.8);
    // Synchronous fallback
    const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
    const binary = atob(dataUrl.split(",")[1]);
    const array = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
    return new Blob([array], { type: "image/jpeg" });
  }, []);

  const drawOverlay = useCallback((dets: Detection[], qr: typeof qrResult) => {
    const overlay = overlayRef.current;
    const video = videoRef.current;
    if (!overlay || !video) return;
    overlay.width = video.videoWidth;
    overlay.height = video.videoHeight;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    // Draw YOLO detections
    for (const det of dets) {
      const [x1, y1, x2, y2] = det.bbox;
      const color = det.class_name === "person" ? "#22c55e" : "#3b82f6";
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.fillStyle = color;
      ctx.font = "bold 12px sans-serif";
      ctx.fillText(`${det.class_name} ${(det.confidence * 100).toFixed(0)}%`, x1, y1 - 4);
    }

    // Draw QR info
    if (qr?.data) {
      ctx.fillStyle = "rgba(0,0,0,0.7)";
      ctx.fillRect(10, overlay.height - 80, 250, 70);
      ctx.fillStyle = "#fff";
      ctx.font = "14px sans-serif";
      ctx.fillText(`QR: ${JSON.stringify(qr.data)}`, 20, overlay.height - 55);
      if (qr.distance !== null) {
        ctx.fillText(`거리: ${qr.distance.toFixed(1)}cm`, 20, overlay.height - 35);
      }
      if (qr.angle !== null) {
        ctx.fillText(`각도: ${qr.angle.toFixed(1)}도`, 20, overlay.height - 15);
      }
    }
  }, []);

  const runDetectionLoop = useCallback(async () => {
    runningRef.current = true;
    let frameCount = 0;
    let lastFpsTime = Date.now();

    while (runningRef.current) {
      const frame = captureFrame();
      if (!frame) {
        await new Promise((r) => setTimeout(r, 200));
        continue;
      }

      let newQr = qrResult;
      let newDets = detections;

      if (mode === "qr" || mode === "hybrid") {
        try {
          const res = await api.decodeQR(frame);
          if (res.success) {
            newQr = { data: res.decoded_data, distance: res.distance_cm, angle: res.angle_deg };
          } else {
            newQr = null;
          }
          setQrResult(newQr);
        } catch { /* ignore */ }
      }

      if (mode === "yolo" || mode === "hybrid") {
        try {
          const res = await api.detect(frame);
          newDets = res.detections || [];
          setDetections(newDets);
        } catch { /* ignore */ }
      }

      drawOverlay(newDets, newQr);

      frameCount++;
      const now = Date.now();
      if (now - lastFpsTime >= 1000) {
        setFps(frameCount);
        frameCount = 0;
        lastFpsTime = now;
      }

      await new Promise((r) => setTimeout(r, 100)); // ~10 FPS max
    }
  }, [mode, captureFrame, drawOverlay, qrResult, detections]);

  useEffect(() => {
    if (cameraActive) {
      runDetectionLoop();
    }
    return () => { runningRef.current = false; };
  }, [cameraActive, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerateQR = async () => {
    const blob = await api.generateQR(qrGenCode);
    const url = URL.createObjectURL(blob);
    setQrImageUrl(url);
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">비전 테스트</h1>
        <p className="text-gray-500 mt-1">맥북 카메라로 QR 인식 및 물체 탐지를 테스트합니다</p>
      </div>

      <div className="flex gap-6">
        {/* Camera View */}
        <div className="flex-1">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: "4/3" }}>
              <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
              <canvas ref={overlayRef} className="absolute inset-0 w-full h-full" />
              {!cameraActive && (
                <div className="absolute inset-0 flex items-center justify-center text-gray-400">
                  카메라가 꺼져 있습니다
                </div>
              )}
              {cameraActive && (
                <div className="absolute top-2 right-2 bg-black/60 text-white px-2 py-1 rounded text-xs">
                  {fps} FPS
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />

            <div className="flex gap-2 mt-3">
              {!cameraActive ? (
                <button onClick={startCamera} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
                  카메라 시작
                </button>
              ) : (
                <button onClick={stopCamera} className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700">
                  카메라 중지
                </button>
              )}
              <div className="flex bg-gray-100 rounded-lg p-0.5">
                {(["qr", "yolo", "hybrid"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      mode === m ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    {m === "qr" ? "QR" : m === "yolo" ? "YOLO" : "하이브리드"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Detection Results */}
          {detections.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mt-4">
              <h3 className="font-semibold text-gray-900 mb-2">탐지 결과</h3>
              <div className="grid grid-cols-3 gap-2">
                {detections.map((d, i) => (
                  <div key={i} className="bg-gray-50 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-900">{d.class_name}</span>
                    <span className="text-gray-500 ml-2">{(d.confidence * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* QR Generator */}
        <div className="w-72 space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold text-gray-900 mb-3">QR 코드 생성</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">쓰레기통 코드</label>
                <input
                  type="text"
                  value={qrGenCode}
                  onChange={(e) => setQrGenCode(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900"
                />
              </div>
              <button
                onClick={handleGenerateQR}
                className="w-full bg-green-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-green-700"
              >
                QR 생성
              </button>
              {qrImageUrl && (
                <div className="text-center">
                  <img src={qrImageUrl} alt="QR Code" className="mx-auto border rounded-lg" width={200} />
                  <a
                    href={qrImageUrl}
                    download={`qr-${qrGenCode}.png`}
                    className="text-sm text-blue-600 hover:underline mt-2 inline-block"
                  >
                    다운로드
                  </a>
                </div>
              )}
            </div>
          </div>

          {qrResult?.data && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="font-semibold text-gray-900 mb-2">QR 인식 결과</h3>
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto text-gray-700">
                {JSON.stringify(qrResult.data, null, 2)}
              </pre>
              {qrResult.distance !== null && (
                <p className="text-sm mt-2 text-gray-600">
                  거리: <span className="font-bold text-gray-900">{qrResult.distance.toFixed(1)}cm</span>
                </p>
              )}
              {qrResult.angle !== null && (
                <p className="text-sm text-gray-600">
                  각도: <span className="font-bold text-gray-900">{qrResult.angle.toFixed(1)}&deg;</span>
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
