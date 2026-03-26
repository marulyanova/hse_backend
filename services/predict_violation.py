import numpy as np
import time

from hse_backend.metrics import (
    PREDICTIONS_TOTAL,
    PREDICTION_DURATION,
    PREDICTION_ERRORS_TOTAL,
    MODEL_PREDICTION_PROBABILITY,
)


def preprocess_features(data):
    return np.array(
        [
            [
                float(data.is_verified_seller),
                data.images_qty / 10.0,
                len(data.description) / 1000.0,
                data.category / 100.0,
            ]
        ]
    )


def predict_violation(model, data):
    start_time = time.time()

    try:
        features = preprocess_features(data)

        inference_start = time.time()
        probability = model.predict_proba(features)[0][1]
        inference_duration = time.time() - inference_start

        PREDICTION_DURATION.labels(model_name="violation_model").observe(
            inference_duration
        )

        is_violation = probability >= 0.5

        result_label = "violation" if is_violation else "no_violation"
        PREDICTIONS_TOTAL.labels(result=result_label).inc()

        MODEL_PREDICTION_PROBABILITY.labels(model_name="violation_model").observe(
            probability
        )

        return {
            "is_violation": bool(is_violation),
            "probability": float(probability),
        }

    except AttributeError as e:
        PREDICTION_ERRORS_TOTAL.labels(error_type="model_unavailable").inc()
        raise
    except Exception as e:
        PREDICTION_ERRORS_TOTAL.labels(error_type="prediction_error").inc()
        raise
