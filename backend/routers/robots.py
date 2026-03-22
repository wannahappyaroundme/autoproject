from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Robot
from schemas import RobotOut

router = APIRouter(prefix="/api/robots", tags=["robots"])


@router.get("", response_model=list[RobotOut])
async def list_robots(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Robot))
    return [RobotOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{robot_id}", response_model=RobotOut)
async def get_robot(robot_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()
    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")
    return RobotOut.model_validate(robot)


@router.patch("/{robot_id}/charge", response_model=RobotOut)
async def charge_robot(robot_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()
    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")
    robot.battery = 100.0
    robot.state = "idle"
    await db.commit()
    await db.refresh(robot)
    return RobotOut.model_validate(robot)
