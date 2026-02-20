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
from repositories.prediction_cache import PredictionCacheStorage
from clients.kafka import KafkaProducer

router = APIRouter()
ad_repo = AdRepository()
moderation_repo = ModerationRepository()
cache_storage = PredictionCacheStorage()
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

    if item_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_id must be a positive integer",
        )

    logging.info(f"Checking cache for item_id={item_id}")
    cached_result = await cache_storage.get_prediction_cache(item_id)
    if cached_result is not None:
        logging.info(f"Cache HIT for item_id={item_id}")
        return cached_result

    logging.info(f"Cache MISS for item_id={item_id}, fetching from DB")

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

        logging.info(f"Saving prediction to cache for item_id={item_id}")
        save_result = await cache_storage.set_prediction_cache(item_id, result)
        logging.info(f"Cache save result: {save_result}")

        return result
    except Exception as e:
        logging.error(f"Prediction failed: {str(e)}")
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

    cached_result = await cache_storage.get_prediction_cache(data.item_id)
    if cached_result is not None:
        logging.info(f"Cache HIT for item_id={data.item_id}, returning cached result")
        # Для асинхронного предсказания возвращаем сразу результат из кэша
        return {
            "task_id": 0,  # 0 означает, что результат уже готов
            "status": "completed",
            "message": "Result returned from cache",
            "is_violation": cached_result.get("is_violation"),
            "probability": cached_result.get("probability"),
        }

    logging.info(f"Cache MISS for item_id={data.item_id}, creating moderation task")

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


@router.delete("/close/{item_id}")
async def close_ad(item_id: int):

    # закрытие объявления и удаление данных по нему

    if item_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_id must be a positive integer",
        )

    try:
        success = await ad_repo.close_ad(item_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ad with item_id = {item_id} not found",
            )

        # Удаляем кэш предсказания из Redis
        await cache_storage.delete_prediction_cache(item_id)

        logging.info(f"Ad closed successfully: item_id={item_id}")

        return {
            "message": f"Ad with item_id = {item_id} closed successfully",
            "item_id": item_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to close ad: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close ad: {str(e)}",
        )
