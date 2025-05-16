from fastapi import FastAPI
from app.api.ostatki import router as ostatki_router

def main():
    app = FastAPI()
    app.include_router(ostatki_router)


    import uvicorn
    uvicorn.run(app, host="192.168.122.18", port=8000)
