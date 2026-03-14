from pydantic import BaseModel
from datetime import datetime


# --- Auth ---
class LoginRequest(BaseModel):
    employee_id: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str
    area_name: str | None = None


class TokenData(BaseModel):
    worker_id: int


# --- Area ---
class AreaOut(BaseModel):
    id: int
    name: str
    address: str
    lat: float
    lon: float
    building_count: int = 0

    model_config = {"from_attributes": True}


# --- Building ---
class BuildingOut(BaseModel):
    id: int
    area_id: int
    name: str
    floors: int
    bin_count: int = 0

    model_config = {"from_attributes": True}


# --- Bin ---
class BinOut(BaseModel):
    id: int
    building_id: int
    bin_code: str
    floor: int
    bin_type: str
    capacity: str
    status: str
    map_x: float
    map_y: float
    qr_data: str | None = None

    model_config = {"from_attributes": True}


class BinCreate(BaseModel):
    building_id: int
    bin_code: str
    floor: int = 1
    bin_type: str = "food_waste"
    capacity: str = "3L"
    map_x: float = 0.0
    map_y: float = 0.0


class BinUpdate(BaseModel):
    bin_code: str | None = None
    floor: int | None = None
    bin_type: str | None = None
    capacity: str | None = None
    status: str | None = None
    map_x: float | None = None
    map_y: float | None = None


# --- Robot ---
class RobotOut(BaseModel):
    id: int
    name: str
    state: str
    battery: float
    position_x: float
    position_y: float
    speed: float
    color: str = "#ef4444"
    current_mission_id: int | None = None

    model_config = {"from_attributes": True}


# --- Mission ---
class MissionCreate(BaseModel):
    area_id: int
    bin_ids: list[int]
    robot_id: int = 1
    priority: str = "normal"


class MissionBinOut(BaseModel):
    id: int
    bin_id: int
    bin_code: str | None = None
    order_index: int
    status: str
    collected_at: datetime | None = None

    model_config = {"from_attributes": True}


class MissionOut(BaseModel):
    id: int
    area_id: int
    worker_id: int | None = None
    robot_id: int | None = None
    status: str
    priority: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_distance: float
    bins: list[MissionBinOut] = []

    model_config = {"from_attributes": True}


# --- Simulation ---
class SimulationPlanRequest(BaseModel):
    bin_ids: list[int]


class PathSegment(BaseModel):
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    path: list[tuple[float, float]]


class SimulationPlanResponse(BaseModel):
    ordered_bin_ids: list[int]
    paths: list[PathSegment]
    total_distance: float
    estimated_time_sec: float


# --- Vision ---
class QRGenerateRequest(BaseModel):
    bin_code: str
    bin_type: str = "food_waste"
    capacity: str = "3L"


class QRDecodeResponse(BaseModel):
    decoded_data: dict | None = None
    corners: list[list[int]] = []
    distance_cm: float | None = None
    angle_deg: float | None = None
    success: bool = False


class DetectionResult(BaseModel):
    class_name: str
    confidence: float
    bbox: list[float]  # [x1, y1, x2, y2]


class DetectionResponse(BaseModel):
    detections: list[DetectionResult]
    inference_time_ms: float
