import asyncio
from uvicorn import Config, Server
from app.api.main import app
from app.bot.main import main as run_bot

async def start_fastapi():
    server = Server(Config(app=app, host="0.0.0.0", port=8000, reload=False))
    await server.serve()

async def start_all():
    await asyncio.gather(
        run_bot(),
        start_fastapi(),
    )

if __name__ == "__main__":
    asyncio.run(start_all())


