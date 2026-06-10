from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import get_health_status

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return get_health_status()
