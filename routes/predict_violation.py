import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, HTTPException, status, Request
import logging

from models.advertisement import Advertisement
from services.predict_violation import predict_violation

router = APIRouter()


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
