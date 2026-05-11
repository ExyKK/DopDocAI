import uvicorn

from app.api import create_app
from app.config import settings

app = create_app()


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        access_log=settings.access_log,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
