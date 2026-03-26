# hse_backend
Репозиторий для ДЗ по курсу ВШЭ "Backend-разработка"

## Структура проекта

```
├── __init__.py
├── clients
│   ├── __init__.py
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
│   ├── __init__.py
│   └── auth.py
├── docker-compose.yml
├── main.py
├── metrics.py
├── ml_models
│   ├── __init__.py
│   ├── model.pkl
│   └── model.py
├── models
│   ├── __init__.py
│   ├── account.py
│   └── advertisement.py
├── prometheus.yml
├── pytest.ini
├── README.md
├── repositories
│   ├── __init__.py
│   ├── accounts.py
│   ├── ads.py
│   ├── moderation.py
│   ├── prediction_cache.py
│   └── users.py
├── requirements.txt
├── routes
│   ├── __init__.py
│   ├── auth.py
│   └── predict_violation.py
├── screencasts
│   ├── demo_kafka.mov
│   ├── Grafana_Screencast.mp4
│   └── prometheus_ok.png
├── services
│   ├── __init__.py
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
    ├── __init__.py
    └── moderation_worker.py
```

--------

## Запуск проекта

**1. Запуск Docker контейнеров (PostgreSQL, Redis, Kafka):**

```sh
docker-compose up -d
```

**2. Запуск миграций БД:**

```sh
cd db
bash start_migration.sh
```

**3. Запуск асинхронного worker для обработки Kafka сообщений (в отдельном терминале):**

```sh
python -m workers.moderation_worker
```

**4. Запуск FastAPI приложения (в отдельном терминале):**

```sh
uvicorn main:app --port 8000
```

Проект запущен и доступен по адресу `http://localhost:8000`

---

## Сервисы и порты

После `docker-compose up -d` сервисы доступны по адресам:

- Kafka (Redpanda): `localhost:9092` (внутри контейнера: `redpanda:29092`)
- Redpanda console (UI kafka): `http://localhost:8080`
- Redis: `localhost:6379`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (админ/пароль по умолчанию `admin/admin`)
- PostgreSQL: `localhost:5435` (DB `service`, user `postgres`, password `postgres`)

--------

## Тестирование

**Запуск всех тестов:**

```sh
pytest tests/ -v
```

**Запуск только unit-тестов (без внешних зависимостей):**

```sh
pytest -m "not integration" -v
```

Unit-тесты проверяют:
- API endpoints
- Бизнес-логику сервисов
- Аутентификацию и авторизацию
- Валидацию моделей

**Запуск только интеграционных тестов (с PostgreSQL, Redis, Kafka):**

```sh
pytest -m "integration" -v
```

Интеграционные тесты проверяют:
- Работу с PostgreSQL (создание, чтение, удаление аккаунтов и объявлений)
- Работу с Redis (кэширование)
- Обработку задач через Kafka и модерационный worker

**Запуск только тестов аутентификации:**

```sh
pytest -m auth -v
```

--------

## Скринкасты

Kafka: https://github.com/marulyanova/hse_backend/blob/main/screencasts/demo_kafka.mov

Grafana: https://github.com/marulyanova/hse_backend/blob/main/screencasts/Grafana_Screencast.mp4

Prometheus: https://github.com/marulyanova/hse_backend/blob/main/screencasts/prometheus_ok.png


--------

## Тестовые примеры из демо Kafka

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

## Тестовые примеры из демо Grafana

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