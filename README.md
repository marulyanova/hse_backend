# hse_backend
Репозиторий для ДЗ по курсу ВШЭ "Backend-разработка"

### Структура проекта

```
├── clients
│   ├── kafka.py
│   ├── postgres.py
│   └── redis.py
├── config
│   └── redis.conf
├── data
│   └── redis
│       └── dump.rdb
├── db
│   ├── migrations
│   │   └── migrations
│   │       ├── V001__create_users_and_ads.sql
│   │       ├── V002__create_moderation_results.sql
│   │       ├── V003__add_is_closed_to_ads.sql
│   │       └── V004__account.sql
│   └── start_migration.sh
├── dependencies
│   └── auth.py
├── docker-compose.yml
├── main.py
├── metrics.py
├── ml_models
│   ├── model.pkl
│   └── model.py
├── models
│   ├── account.py
│   └── advertisement.py
├── prometheus.yml
├── pytest.uni
├── README.md
├── repositories
│   ├── accounts.py
│   ├── ads.py
│   ├── moderation.py
│   ├── prediction_cache.py
│   └── users.py
├── requirements.txt
├── routes
│   ├── auth.py
│   └── predict_violation.py
├── screencasts
│   ├── demo_kafka.mov
│   ├── Grafana_Screencast.mp4
│   └── prometheus_ok.png
├── services
│   ├── auth.py
│   └── predict_violation.py
├── tests
│   ├── conftest.py
│   ├── test_accounts_repo.py
│   ├── test_adds.py
│   ├── test_auth_dependency.py
│   ├── test_auth_routes.py
│   ├── test_auth_service.py
│   ├── test_prediction_cache.py
│   ├── test_violation_model_with_db.py
│   └── test_violation_model.py
└── workers
    └── moderation_worker.py
```

--------

### Запуск

**Запуск миграций:**

```sh
cd db
bash start_migration.sh
```

**Запуск Docker**

```sh
docker-compose up -d
```

**Запуск worker**
```sh
python -m workers.moderation_worker
```

**Запуск FastAPI приложения**
```sh
uvicorn main:app --port 8000
```

--------

### Тесты для ДЗ Безопасность и аутентификация 

```sh
pytest tests/test_accounts_repo.py && pytest tests/test_auth_service.py && pytest tests/test_auth_routes.py && pytest tests/test_auth_dependency.py
```

или

```sh
pytest -m "auth" -v
```

--------

### Тестовые примеры из демо Kafka

```
INSERT INTO users (id, is_verified) VALUES (3337, false);

INSERT INTO ads (seller_id, item_id, name, description, category, images_qty) VALUES (3337, 9078, 'Тест название 1', 'Тест описание 1', 2, 0);

curl -X POST http://localhost:8000/predict/async_predict \
  -H "Content-Type: application/json" \
  -d '{"item_id": 9078}'

curl http://localhost:8000/predict/moderation_result/1

SELECT * FROM moderation_results WHERE item_id = 9078;


INSERT INTO users (id, is_verified) VALUES (99068, false);

INSERT INTO ads (seller_id, item_id, name, description, category, images_qty) VALUES (99068, 23345, 'Тест название 2', 'Тест описание 2', 2, 1);

curl -X POST http://localhost:8000/predict/async_predict \
  -H "Content-Type: application/json" \
  -d '{"item_id": 23345}'

curl http://localhost:8000/predict/moderation_result/2

SELECT * FROM moderation_results WHERE item_id = 23345;
```

### Запуск только интеграционных тестов

```sh
pytest -m integration -v
```

Запуск только юнит-тестов

```sh
pytest -m "not integration" -v
```

### Тестовые примеры из демо Grafana

```
-Обычные
- no_violation:
curl -X POST http://localhost:8000/predict/ -H "Content-Type: application/json" -d '{"seller_id":1,"item_id":123,"is_verified_seller":true,"images_qty":3,"category":1,"name":"Test Product","description":"xTest description for moderation"}'

-violation:
curl -X POST http://localhost:8000/predict/ -H "Content-Type: application/json" -d '{"seller_id":999,"item_id":777,"is_verified_seller":false,"images_qty":0,"category":99,"name":"Suspicious Ad","description":"x"}'

curl -X POST http://localhost:8000/predict/ -H "Content-Type: application/json" -d '{"seller_id":101,"item_id":888,"is_verified_seller":false,"images_qty":0,"category":50,"name":"Quick Sale","description":"buy now"}'

- Взаимодействие с БД
- Создание тестового пользователя
INSERT INTO users (id, is_verified) VALUES (100, false) ON CONFLICT (id) DO NOTHING;

Создание тестового объявления
INSERT INTO ads (seller_id, item_id, name, description, category, images_qty, is_closed) VALUES (100, 1000, 'Test async ad', 'Test description', 1, 0, false) ON CONFLICT (item_id) DO NOTHING;

curl -s -X POST http://localhost:8000/predict/async_predict -H "Content-Type: application/json" -d '{"item_id":1000}'

Создание тестового пользователя
INSERT INTO users (id, is_verified) VALUES (12345, true) ON CONFLICT (id) DO NOTHING;

Создание тестового объявления
INSERT INTO ads (seller_id, item_id, name, description, category, images_qty, is_closed) VALUES (12345, 123450, 'Test async ad 2', 'Test description 2', 1, 0, false) ON CONFLICT (item_id) DO NOTHING;

curl -s -X POST http://localhost:8000/predict/async_predict -H "Content-Type: application/json" -d '{"item_id": 123450}'
curl -s http://localhost:8000/predict/moderation_result/1

- Вызов ошибок
curl -s http://localhost:8000/predict/simple_predict/-1
curl -s http://localhost:8000/predict/simple_predict/abc
```