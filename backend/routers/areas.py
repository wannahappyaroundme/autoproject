from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Area, Building, Bin
from schemas import AreaOut, BuildingOut

router = APIRouter(prefix="/api/areas", tags=["areas"])


@router.get("", response_model=list[AreaOut])
async def list_areas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area))
    areas = result.scalars().all()

    out = []
    for area in areas:
        count_result = await db.execute(
            select(func.count(Building.id)).where(Building.area_id == area.id)
        )
        count = count_result.scalar() or 0
        out.append(AreaOut(
            id=area.id, name=area.name, address=area.address,
            lat=area.lat, lon=area.lon, building_count=count,
        ))
    return out


@router.get("/{area_id}/buildings", response_model=list[BuildingOut])
async def list_buildings(area_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Building).where(Building.area_id == area_id))
    buildings = result.scalars().all()

    out = []
    for bldg in buildings:
        count_result = await db.execute(
            select(func.count(Bin.id)).where(Bin.building_id == bldg.id)
        )
        count = count_result.scalar() or 0
        out.append(BuildingOut(
            id=bldg.id, area_id=bldg.area_id, name=bldg.name,
            floors=bldg.floors, bin_count=count,
        ))
    return out
