from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Mission, MissionBin, Bin, MissionStatus
from schemas import MissionCreate, MissionOut, MissionBinOut

router = APIRouter(prefix="/api/missions", tags=["missions"])


def _format_mission(mission: Mission) -> MissionOut:
    bins_out = []
    for mb in mission.mission_bins:
        bins_out.append(MissionBinOut(
            id=mb.id, bin_id=mb.bin_id,
            bin_code=mb.bin.bin_code if mb.bin else None,
            order_index=mb.order_index, status=mb.status,
            collected_at=mb.collected_at,
        ))
    return MissionOut(
        id=mission.id, area_id=mission.area_id,
        worker_id=mission.worker_id, robot_id=mission.robot_id,
        status=mission.status, priority=mission.priority,
        created_at=mission.created_at, started_at=mission.started_at,
        completed_at=mission.completed_at, total_distance=mission.total_distance,
        bins=bins_out,
    )


@router.get("", response_model=list[MissionOut])
async def list_missions(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Mission).options(
        selectinload(Mission.mission_bins).selectinload(MissionBin.bin)
    ).order_by(Mission.created_at.desc())
    if status:
        query = query.where(Mission.status == status)
    result = await db.execute(query)
    return [_format_mission(m) for m in result.scalars().all()]


@router.post("", response_model=MissionOut)
async def create_mission(data: MissionCreate, db: AsyncSession = Depends(get_db)):
    mission = Mission(area_id=data.area_id, priority=data.priority, robot_id=data.robot_id)
    db.add(mission)
    await db.flush()

    for idx, bin_id in enumerate(data.bin_ids):
        bin_result = await db.execute(select(Bin).where(Bin.id == bin_id))
        b = bin_result.scalar_one_or_none()
        if not b:
            raise HTTPException(status_code=404, detail=f"Bin {bin_id} not found")
        mb = MissionBin(mission_id=mission.id, bin_id=bin_id, order_index=idx)
        db.add(mb)

    await db.commit()

    result = await db.execute(
        select(Mission).options(
            selectinload(Mission.mission_bins).selectinload(MissionBin.bin)
        ).where(Mission.id == mission.id)
    )
    return _format_mission(result.scalar_one())


@router.get("/{mission_id}", response_model=MissionOut)
async def get_mission(mission_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Mission).options(
            selectinload(Mission.mission_bins).selectinload(MissionBin.bin)
        ).where(Mission.id == mission_id)
    )
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _format_mission(mission)


@router.post("/{mission_id}/start")
async def start_mission(mission_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.status = MissionStatus.in_progress.value
    mission.started_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Mission started", "mission_id": mission_id}


@router.post("/{mission_id}/cancel")
async def cancel_mission(mission_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.status = MissionStatus.cancelled.value
    await db.commit()
    return {"detail": "Mission cancelled", "mission_id": mission_id}
