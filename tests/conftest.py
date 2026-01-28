import pytest

INVALID_PAYLOADS = [
    # нет images_qty
    {
        "seller_id": 123,
        "is_verified_seller": True,
        "item_id": 456,
        "name": "товар",
        "description": "описание",
        "category": 1,
    },
    # неправильные типы seller_id, is_verified_seller, item_id
    {
        "seller_id": "first",
        "is_verified_seller": 1.0,
        "item_id": "first",
        "name": "товар",
        "description": "описание",
        "category": 1,
        "images_qty": 3,
    },
    # пустой объект
    {},
]


@pytest.fixture
def invalid_payloads():
    return INVALID_PAYLOADS
