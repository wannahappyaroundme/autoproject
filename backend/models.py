from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
import enum


class MissionStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class RobotState(str, enum.Enum):
    idle = "idle"
    navigating = "navigating"
    grasping = "grasping"
    returning = "returning"
    error = "error"


class BinStatus(str, enum.Enum):
    registered = "registered"
    pending = "pending"
    collected = "collected"


class Area(Base):
    __tablename__ = "areas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    lat = Column(Float, default=0.0)
    lon = Column(Float, default=0.0)
    buildings = relationship("Building", back_populates="area", cascade="all, delete-orphan")


class Building(Base):
    __tablename__ = "buildings"
    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False)
    name = Column(String, nullable=False)
    floors = Column(Integer, default=1)
    area = relationship("Area", back_populates="buildings")
    bins = relationship("Bin", back_populates="building", cascade="all, delete-orphan")


class Bin(Base):
    __tablename__ = "bins"
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    bin_code = Column(String, unique=True, nullable=False)
    floor = Column(Integer, default=1)
    bin_type = Column(String, default="food_waste")
    capacity = Column(String, default="3L")
    status = Column(String, default=BinStatus.registered.value)
    map_x = Column(Float, default=0.0)
    map_y = Column(Float, default=0.0)
    qr_data = Column(Text, nullable=True)
    building = relationship("Building", back_populates="bins")


class Worker(Base):
    __tablename__ = "workers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    employee_id = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True)


class Robot(Base):
    __tablename__ = "robots"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    state = Column(String, default=RobotState.idle.value)
    battery = Column(Float, default=100.0)
    position_x = Column(Float, default=0.0)
    position_y = Column(Float, default=0.0)
    speed = Column(Float, default=0.0)
    color = Column(String, default="#ef4444")
    current_mission_id = Column(Integer, ForeignKey("missions.id"), nullable=True)


class Mission(Base):
    __tablename__ = "missions"
    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=True)
    status = Column(String, default=MissionStatus.pending.value)
    priority = Column(String, default="normal")
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    total_distance = Column(Float, default=0.0)
    mission_bins = relationship("MissionBin", back_populates="mission", cascade="all, delete-orphan")


class MissionBin(Base):
    __tablename__ = "mission_bins"
    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False)
    bin_id = Column(Integer, ForeignKey("bins.id"), nullable=False)
    order_index = Column(Integer, default=0)
    status = Column(String, default="pending")
    collected_at = Column(DateTime, nullable=True)
    mission = relationship("Mission", back_populates="mission_bins")
    bin = relationship("Bin")
