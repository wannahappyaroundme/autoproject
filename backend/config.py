import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/robot_sim.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://wannahappyaroundme.github.io",
    os.getenv("FRONTEND_URL", ""),
]
CORS_ORIGINS = [u for u in CORS_ORIGINS if u]  # 빈 문자열 제거
