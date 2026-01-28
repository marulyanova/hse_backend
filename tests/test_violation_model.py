import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from http import HTTPStatus
import pytest

from main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_root(client):
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["message"] == "Hello World"


# решающее правило y = (X[:, 0] < 0.3) & (X[:, 1] < 0.2)
# Признаки: [is_verified_seller, images_qty, description_length, category]


@pytest.mark.parametrize(
    "input_data, expected_is_violation",
    [
        # not violation - float(is_verified_seller) = 1.0 >= 0.3, images_qty / 10.0 = 0.5 > 0.2
        (
            {
                "seller_id": 8237,
                "is_verified_seller": True,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 5,
            },
            False,
        ),
        # not violation - float(is_verified_seller) = 1.0 >= 0.3, images_qty / 10.0 = 0.1 < 0.2
        (
            {
                "seller_id": 8237,
                "is_verified_seller": True,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 1,
            },
            False,
        ),
        # not violation - float(is_verified_seller) = 0.0 >= 0.3, images_qty / 10.0 = 0.5 > 0.2
        (
            {
                "seller_id": 8237,
                "is_verified_seller": False,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 5,
            },
            False,
        ),
        # violation - float(is_verified_seller) = 0.0 < 0.3, images_qty / 10.0 = 0.1 < 0.2
        (
            {
                "seller_id": 8237,
                "is_verified_seller": False,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 1,
            },
            True,
        ),
        # violation - float(is_verified_seller) = 0.0 < 0.3, images_qty / 10.0 = 0.0 < 0.2
        (
            {
                "seller_id": 8237,
                "is_verified_seller": False,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 0,
            },
            True,
        ),
    ],
)
def test_predict_violation(client, input_data, expected_is_violation):
    response = client.post("/predict", json=input_data)
    assert response.status_code == HTTPStatus.OK

    result = response.json()
    assert result["is_violation"] is expected_is_violation
    assert isinstance(result["probability"], float)
    assert 0.0 <= result["probability"] <= 1.0


def test_params_validation(client, invalid_payloads):
    for payload in invalid_payloads:
        response = client.post("/predict", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
