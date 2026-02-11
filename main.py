import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
import logging

from ml_models.model import train_model, save_model, load_model
from routes.predict_violation import router as predict_violation_router
from clients.kafka import KafkaProducer

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.models = {}

    model_dir = BASE_DIR / "ml_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    violation_model_path = model_dir / "model.pkl"

    if os.path.exists(violation_model_path):
        app.state.models["violation_model"] = load_model(violation_model_path)
    else:
        model = train_model()
        save_model(model, violation_model_path)
        app.state.models["violation_model"] = model

    if "violation_model" not in app.state.models:
        raise RuntimeError("Failed to load or train the violation model")

    kafka_producer = KafkaProducer(bootstrap_servers="localhost:9092")
    await kafka_producer.start()
    app.state.kafka_producer = kafka_producer

    yield

    await kafka_producer.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(predict_violation_router, prefix="/predict")


@app.get("/")
async def root():
    return {"message": "Hello World"}
