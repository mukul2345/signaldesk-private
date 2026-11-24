import uvicorn

from signaldesk.config import load_settings


if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(
        "signaldesk.main:app",
        host=settings.runtime.api_host,
        port=settings.runtime.api_port,
        reload=False,
    )
