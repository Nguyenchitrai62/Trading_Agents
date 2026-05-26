from BE.config import SETTINGS
from BE.server import app


__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=SETTINGS.port)