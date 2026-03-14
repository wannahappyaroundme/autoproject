"""Sample data seeding for development/testing."""
import asyncio
import json
import bcrypt
from database import engine, async_session, Base
from models import Area, Building, Bin, Worker, Robot


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

AREAS = [
    {"name": "래미안 1단지", "address": "서울시 강남구 래미안로 1", "lat": 37.5012, "lon": 127.0396},
    {"name": "힐스테이트 2단지", "address": "서울시 서초구 힐스테이트로 2", "lat": 37.4950, "lon": 127.0320},
]

BUILDINGS_PER_AREA = [
    ["101동", "102동", "103동", "104동", "105동"],
    ["201동", "202동", "203동", "204동", "205동"],
]

# Map positions for bins (grid coordinates for 2D simulation)
BIN_POSITIONS = [
    # Area 1 bins - scattered around apartment complex
    [(5, 3), (5, 7), (12, 3), (12, 7), (18, 3), (18, 7), (25, 3), (25, 7), (8, 12), (15, 12)],
    [(5, 3), (5, 7), (12, 3), (12, 7), (18, 3), (18, 7), (25, 3), (25, 7), (8, 12), (15, 12)],
    [(5, 18), (5, 22), (12, 18), (12, 22), (18, 18), (18, 22), (25, 18), (25, 22), (8, 27), (15, 27)],
    [(5, 18), (5, 22), (12, 18), (12, 22), (18, 18), (18, 22), (25, 18), (25, 22), (8, 27), (15, 27)],
    [(5, 33), (5, 37), (12, 33), (12, 37), (18, 33), (18, 37), (25, 33), (25, 37), (8, 38), (15, 38)],
    # Area 2 bins
    [(5, 3), (5, 7), (12, 3), (12, 7), (18, 3), (18, 7), (25, 3), (25, 7), (8, 12), (15, 12)],
    [(5, 3), (5, 7), (12, 3), (12, 7), (18, 3), (18, 7), (25, 3), (25, 7), (8, 12), (15, 12)],
    [(5, 18), (5, 22), (12, 18), (12, 22), (18, 18), (18, 22), (25, 18), (25, 22), (8, 27), (15, 27)],
    [(5, 18), (5, 22), (12, 18), (12, 22), (18, 18), (18, 22), (25, 18), (25, 22), (8, 27), (15, 27)],
    [(5, 33), (5, 37), (12, 33), (12, 37), (18, 33), (18, 37), (25, 33), (25, 37), (8, 38), (15, 38)],
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        bin_pos_idx = 0
        for area_idx, area_data in enumerate(AREAS):
            area = Area(**area_data)
            session.add(area)
            await session.flush()

            for bldg_name in BUILDINGS_PER_AREA[area_idx]:
                building = Building(area_id=area.id, name=bldg_name, floors=15)
                session.add(building)
                await session.flush()

                positions = BIN_POSITIONS[bin_pos_idx % len(BIN_POSITIONS)]
                bin_pos_idx += 1

                for floor_idx in range(1, 11):  # 10 bins per building
                    pos = positions[(floor_idx - 1) % len(positions)]
                    bin_code = f"{bldg_name}-{floor_idx:02d}"
                    qr_payload = json.dumps({
                        "bin_id": bin_code,
                        "type": "food_waste",
                        "capacity": "3L",
                        "area": area_data["name"],
                        "building": bldg_name,
                    }, ensure_ascii=False)

                    b = Bin(
                        building_id=building.id,
                        bin_code=bin_code,
                        floor=floor_idx,
                        bin_type="food_waste",
                        capacity="3L",
                        map_x=float(pos[0] + area_idx * 35),
                        map_y=float(pos[1]),
                        qr_data=qr_payload,
                    )
                    session.add(b)

        # Workers
        workers = [
            Worker(name="홍길동", employee_id="ENV-001", password_hash=hash_password("1234"), area_id=1),
            Worker(name="김철수", employee_id="ENV-002", password_hash=hash_password("1234"), area_id=2),
        ]
        session.add_all(workers)

        # Robots (최대 4대 운용)
        robots = [
            Robot(name="로봇-001", state="idle", battery=100.0, position_x=35.0, position_y=0.0, color="#ef4444"),
            Robot(name="로봇-002", state="idle", battery=85.0, position_x=35.0, position_y=0.0, color="#3b82f6"),
            Robot(name="로봇-003", state="idle", battery=92.0, position_x=35.0, position_y=0.0, color="#22c55e"),
            Robot(name="로봇-004", state="idle", battery=78.0, position_x=35.0, position_y=0.0, color="#f59e0b"),
        ]
        session.add_all(robots)

        await session.commit()
        print("Seed data created: 2 areas, 10 buildings, 100 bins, 2 workers, 4 robots")


if __name__ == "__main__":
    asyncio.run(seed())
