import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, HTTPException, status, Request
import logging

from models.advertisement import (
    Advertisement,
    AsyncPredictResponse,
    AsyncPredictRequest,
    ModerationResultResponse,
)
from services.predict_violation import predict_violation
from repositories.ads import AdRepository
from repositories.moderation import ModerationRepository, ModerationResultNotFoundError
from clients.kafka import KafkaProducer

router = APIRouter()
ad_repo = AdRepository()
moderation_repo = ModerationRepository()
kafka_producer = KafkaProducer(bootstrap_servers="localhost:9092")


@router.post("/")
async def violation_predictor(request: Request, data: Advertisement):

    logging.info(
        f"Request received: seller_id = {data.seller_id}, item_id = {data.item_id}, "
        f"is_verified = {data.is_verified_seller}, images_qty = {data.images_qty}, category = {data.category}"
    )

    model = request.app.state.models.get("violation_model")

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML model is not loaded",
        )

    try:
        result = predict_violation(model, data)
        logging.info(
            f"Prediction result for item_id = {data.item_id}: "
            f"is_violation = {result['is_violation']}, probability = {result['probability']}"
        )
        return result
    except Exception as e:
        logging.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed with error: {e}",
        )


@router.post("/naive")
async def violation_predictor_naive(data: Advertisement):
    if data.is_verified_seller:
        return {"is_violation": False}
    else:
        return {"is_violation": data.images_qty == 0}


@router.get("/simple_predict/{item_id}")
async def simple_predict(request: Request, item_id: int) -> dict:

    # валидация item_id, должно быть положительным целым числом
    if item_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_id must be a positive integer",
        )

    ad_data = await ad_repo.get_ad_with_seller(item_id)
    if not ad_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ad with item_id = {item_id} not found",
        )

    try:
        ad_model = Advertisement(**ad_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data inconsistency in ad with item_id = {item_id}: {e}",
        )

    model = request.app.state.models.get("violation_model")
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML model is not loaded",
        )

    try:
        result = predict_violation(model, ad_model)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}",
        )


@router.post("/async_predict", response_model=AsyncPredictResponse)
async def async_predict(request: Request, data: AsyncPredictRequest):
    if data.item_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_id must be a positive integer",
        )

    ad_data = await ad_repo.get_ad_with_seller(data.item_id)
    if not ad_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ad not found",
        )

    moderation_record = await moderation_repo.create_pending(data.item_id)
    task_id = moderation_record["id"]

    kafka_prod = request.app.state.kafka_producer
    await kafka_prod.send_moderation_request(data.item_id)

    return AsyncPredictResponse(
        task_id=task_id, status="pending", message="Moderation request accepted"
    )


@router.get("/moderation_result/{task_id}", response_model=ModerationResultResponse)
async def get_moderation_result(task_id: int):
    if task_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id must be a positive integer",
        )

    try:
        record = await moderation_repo.get_by_id(task_id)
    except ModerationResultNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id = {task_id} not found",
        )

    return ModerationResultResponse(
        task_id=record["id"],
        status=record["status"],
        is_violation=record.get("is_violation"),
        probability=record.get("probability"),
    )
