import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient
from http import HTTPStatus
import pytest

from hse_backend.main import app

pytestmark = [pytest.mark.unit]


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["message"] == "Hello World"


@pytest.mark.parametrize(
    "input_data, expected_is_violation",
    [
        # verified - not violation
        (
            {
                "seller_id": 8237,
                "is_verified_seller": True,
                "item_id": 5602,
                "name": "название товара",
                "description": "описание товара",
                "category": 1,
                "images_qty": 0,
            },
            False,
        ),
        # unverified, есть изображения - not violation
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
        # unverified, нет изображений violation
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
def test_naive_predictor(client, input_data, expected_is_violation):
    response = client.post("/predict/naive", json=input_data)
    assert response.status_code == HTTPStatus.OK
    result = response.json()
    assert result["is_violation"] is expected_is_violation


def test_params_validation(client, invalid_payloads):
    for payload in invalid_payloads:
        response = client.post("/predict/naive", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
