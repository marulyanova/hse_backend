import numpy as np


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
    features = preprocess_features(data)
    probability = model.predict_proba(features)[0][1]
    is_violation = probability >= 0.5

    return {
        "is_violation": bool(is_violation),
        "probability": float(probability),
    }
