import argparse
import os

import uvicorn

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FastAPI + MAX bot")
    parser.add_argument(
        "--mode",
        choices=("polling", "webhook"),
        default=settings.BOT_RUN_MODE,
        help="Bot delivery mode: long polling for dev or webhook for production.",
    )
    args = parser.parse_args()

    os.environ["BOT_RUN_MODE"] = args.mode

    uvicorn.run(
        "app.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
