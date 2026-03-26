from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import os
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hse_backend.ml_models.model import train_model, save_model, load_model
from hse_backend.routes.predict_violation import router as predict_violation_router
from hse_backend.routes.auth import router as auth_router
from hse_backend.clients.kafka import KafkaProducer
from hse_backend.clients.redis import redis_client
from hse_backend.clients.postgres import init_pool, close_pool

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from hse_backend.metrics import REQUEST_COUNT, REQUEST_DURATION

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

    await init_pool()

    await redis_client.connect()
    app.state.redis_client = redis_client

    kafka_producer = KafkaProducer(bootstrap_servers="localhost:9092")
    await kafka_producer.start()
    app.state.kafka_producer = kafka_producer

    yield

    await kafka_producer.stop()
    await redis_client.close()
    await close_pool()


class NoopKafkaProducer:
    async def start(self):
        return None

    async def stop(self):
        return None

    async def send_moderation_request(self, item_id):
        logging.info(f"NoopKafkaProducer: send_moderation_request({item_id})")
        return None


app = FastAPI(lifespan=lifespan)
app.state.kafka_producer = NoopKafkaProducer()
app.add_middleware(PrometheusMiddleware)


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(predict_violation_router, prefix="/predict")
app.include_router(auth_router, prefix="")


@app.get("/")
async def root():
    return {"message": "Hello World"}
