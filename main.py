import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import os
import logging

from ml_models.model import train_model, save_model, load_model
from routes.predict_violation import router as predict_violation_router
from routes.auth import router as auth_router
from clients.kafka import KafkaProducer
from clients.redis import redis_client

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from metrics import REQUEST_COUNT, REQUEST_DURATION

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path.split("?")[0]
        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=method, endpoint=endpoint, status=status_code
            ).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return response


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

    await redis_client.connect()
    app.state.redis_client = redis_client

    kafka_producer = KafkaProducer(bootstrap_servers="localhost:9092")
    await kafka_producer.start()
    app.state.kafka_producer = kafka_producer

    yield

    await kafka_producer.stop()
    await redis_client.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(PrometheusMiddleware)


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(predict_violation_router, prefix="/predict")
app.include_router(auth_router, prefix="")


@app.get("/")
async def root():
    return {"message": "Hello World"}
