from app.core.config import get_settings
from app.schemas.health import HealthResponse


def get_health_status() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
    )
