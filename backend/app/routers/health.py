from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
@router.get("/", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        app=settings.app_name,
        time=datetime.now(timezone.utc),
    )
