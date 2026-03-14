from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from database import get_db
from models import Worker, Area
from schemas import LoginRequest, LoginResponse
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/api/auth", tags=["auth"])


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Worker).where(Worker.employee_id == req.employee_id))
    worker = result.scalar_one_or_none()

    if not worker or not verify_password(req.password, worker.password_hash):
        raise HTTPException(status_code=401, detail="직원번호 또는 비밀번호가 일치하지 않습니다")

    area_name = None
    if worker.area_id:
        area_result = await db.execute(select(Area).where(Area.id == worker.area_id))
        area = area_result.scalar_one_or_none()
        area_name = area.name if area else None

    token = create_access_token({"sub": str(worker.id)})
    return LoginResponse(token=token, name=worker.name, area_name=area_name)
