from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Bin
from schemas import BinOut, BinCreate, BinUpdate

router = APIRouter(prefix="/api/bins", tags=["bins"])


@router.get("", response_model=list[BinOut])
async def list_bins(
    area_id: int | None = Query(None),
    building_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Bin)
    if building_id:
        query = query.where(Bin.building_id == building_id)
    elif area_id:
        from models import Building
        query = query.join(Building).where(Building.area_id == area_id)
    result = await db.execute(query)
    return [BinOut.model_validate(b) for b in result.scalars().all()]


@router.post("", response_model=BinOut)
async def create_bin(data: BinCreate, db: AsyncSession = Depends(get_db)):
    b = Bin(**data.model_dump())
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return BinOut.model_validate(b)


@router.put("/{bin_id}", response_model=BinOut)
async def update_bin(bin_id: int, data: BinUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Bin not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(b, key, val)
    await db.commit()
    await db.refresh(b)
    return BinOut.model_validate(b)


@router.delete("/{bin_id}")
async def delete_bin(bin_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bin).where(Bin.id == bin_id))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Bin not found")
    await db.delete(b)
    await db.commit()
    return {"detail": "Deleted"}
