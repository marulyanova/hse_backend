# hse_backend
Репозиторий для ДЗ по курсу ВШЭ "Backend-разработка"

Запуск миграций:

```sh
cd db
bash start_migration.sh
```

Запуск Docker

```sh
docker-compose up -d
```

Запуск worker
```sh
python -m workers.moderation_worker
```

Запуск FastAPI приложения
```sh
uvicorn main:app --port 8000
```

Тестовые примеры из демо
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

Запуск только интеграционных тестов

```sh
pytest -m integration -v
```

Запуск только юнит-тестов

```sh
pytest -m "not integration" -v
```