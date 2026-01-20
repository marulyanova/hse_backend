import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from http import HTTPStatus
import pytest

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["message"] == "Hello World"


def test_predictor_positive(client):

    # verified
    params = {
        "seller_id": 8237,
        "is_verified_seller": True,
        "item_id": 5602,
        "name": "название товара",
        "description": "описание товара",
        "category": 1,
        "images_qty": 0,
    }

    response = client.post("/predict", json=params)
    assert response.status_code == HTTPStatus.OK
    assert response.json() is True

    # unverified, есть изображения
    params["is_verified_seller"] = False
    params["images_qty"] = 5

    response = client.post("/predict", json=params)
    assert response.status_code == HTTPStatus.OK
    assert response.json() is True


def test_predictor_negative(client):

    params = {
        "seller_id": 8237,
        "is_verified_seller": False,
        "item_id": 5602,
        "name": "название товара",
        "description": "описание товара",
        "category": 1,
        "images_qty": 0,
    }

    response = client.post("/predict", json=params)
    assert response.status_code == HTTPStatus.OK
    assert response.json() is False


def test_params_validation(client):

    # указаны не все параметры
    params = {
        "seller_id": 8237,
        "description": "описание товара",
        "category": 1,
        "images_qty": 0,
    }

    response = client.post("/predict", json=params)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # параметры не того типа
    params = {
        "seller_id": "id пользователя",
        "is_verified_seller": "да",
        "item_id": 5602,
        "name": "название товара",
        "description": "описание товара",
        "category": "название категории",
        "images_qty": 5,
    }

    response = client.post("/predict", json=params)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


if __name__ == "__main__":
    pytest.main()
