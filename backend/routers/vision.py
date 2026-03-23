import base64
import io
import json
import time

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from schemas import QRGenerateRequest, QRDecodeResponse, DetectionResponse, DetectionResult
from vision.qr_generator import generate_qr_image

try:
    import cv2
    import numpy as np
    from vision.qr_reader import decode_qr
    from vision.distance_estimator import estimate_distance_from_qr
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

router = APIRouter(prefix="/api/vision", tags=["vision"])

# Lazy-loaded YOLO model
_yolo_model = None


def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolo11n.pt")
    return _yolo_model


@router.post("/qr/generate")
async def generate_qr(req: QRGenerateRequest):
    payload = json.dumps({
        "bin_id": req.bin_code,
        "type": req.bin_type,
        "capacity": req.capacity,
    }, ensure_ascii=False)
    img_bytes = generate_qr_image(payload)
    return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")


@router.post("/qr/decode", response_model=QRDecodeResponse)
async def decode_qr_endpoint(file: UploadFile = File(...)):
    if not HAS_CV2:
        return QRDecodeResponse(success=False, data=None, message="OpenCV not available on this server")
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return QRDecodeResponse(success=False)

    decoded = decode_qr(frame)
    if not decoded:
        return QRDecodeResponse(success=False)

    qr = decoded[0]
    corners = [[int(p.x), int(p.y)] for p in qr.polygon] if hasattr(qr, 'polygon') else []

    try:
        data = json.loads(qr.data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {"raw": qr.data.decode("utf-8", errors="replace")}

    distance_cm, angle_deg = None, None
    if len(corners) == 4:
        distance_cm, angle_deg = estimate_distance_from_qr(corners, qr_size_cm=10.0)

    return QRDecodeResponse(
        decoded_data=data,
        corners=corners,
        distance_cm=round(distance_cm, 1) if distance_cm else None,
        angle_deg=round(angle_deg, 1) if angle_deg else None,
        success=True,
    )


@router.post("/detect", response_model=DetectionResponse)
async def detect_objects(file: UploadFile = File(...)):
    if not HAS_CV2:
        return DetectionResponse(detections=[], count=0, inference_ms=0)
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return DetectionResponse(detections=[], inference_time_ms=0)

    model = _get_yolo()
    start = time.time()
    results = model(frame, verbose=False)
    inference_ms = (time.time() - start) * 1000

    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append(DetectionResult(
                class_name=model.names[cls_id],
                confidence=round(conf, 3),
                bbox=[round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            ))

    return DetectionResponse(detections=detections, inference_time_ms=round(inference_ms, 1))
