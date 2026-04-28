"""Local entrypoint: `python main.py` runs the API on :8000."""
import uvicorn

from pradapicks.api import app
from pradapicks.db import init_db


if __name__ == "__main__":
    init_db()
    uvicorn.run("pradapicks.api:app", host="0.0.0.0", port=8000, reload=False)
