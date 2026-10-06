import uvicorn

from .config import Settings


if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "backend.app.server:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )
