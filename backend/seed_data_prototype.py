"""시제품 테스트용 시드 데이터 — 소형 테스트 랩, 로봇 2대, 쓰레기통 4개."""
import asyncio
import json
import bcrypt
from database import engine, async_session, Base
from models import Area, Building, Bin, Worker, Robot


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # 테스트 구역
        area = Area(
            name="시제품 테스트 랩",
            address="테스트 공간",
            lat=37.5,
            lon=127.0,
        )
        session.add(area)
        await session.flush()

        # 가상 건물 (테스트 랩)
        building = Building(area_id=area.id, name="테스트 랩", floors=1)
        session.add(building)
        await session.flush()

        # 쓰레기통 4개 (40×30 소형 아파트 단지 좌표)
        bin_data = [
            ("BIN-01", 12, 7, "full"),
            ("BIN-02", 27, 7, "full"),
            ("BIN-03", 12, 20, "half"),
            ("BIN-04", 27, 20, "half"),
        ]
        for code, mx, my, status in bin_data:
            qr_payload = json.dumps({
                "bin_id": code,
                "type": "food_waste",
                "capacity": "3L",
                "area": "시제품 테스트 랩",
            }, ensure_ascii=False)
            b = Bin(
                building_id=building.id,
                bin_code=code,
                floor=1,
                bin_type="food_waste",
                capacity="3L",
                status=status,
                map_x=float(mx),
                map_y=float(my),
                qr_data=qr_payload,
            )
            session.add(b)

        # 작업자
        worker = Worker(
            name="테스트 관리자",
            employee_id="TEST-001",
            password_hash=hash_password("1234"),
            area_id=area.id,
        )
        session.add(worker)

        # 로봇 2대
        robots = [
            Robot(name="로봇-A", state="idle", battery=100.0, position_x=3.0, position_y=27.0, color="#ef4444"),
            Robot(name="로봇-B", state="idle", battery=100.0, position_x=36.0, position_y=27.0, color="#3b82f6"),
        ]
        session.add_all(robots)

        await session.commit()
        print("시제품 시드 데이터 생성 완료: 1 구역, 1 건물, 4 쓰레기통, 1 작업자, 2 로봇")


if __name__ == "__main__":
    asyncio.run(seed())
