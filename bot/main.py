from fastapi import FastAPI


app = FastAPI()


@app.get("/")
async def root():
    hotels = [{
        "name": "KRAVT",
        "price": 5000,
        "city": "Kazan"
    }]

    return hotels