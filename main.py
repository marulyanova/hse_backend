from fastapi import FastAPI
from models.advertisement import Advertisement

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/predict")
async def predictor(data: Advertisement) -> bool:

    if data.is_verified_seller:
        return True
    else:
        return data.images_qty > 0
