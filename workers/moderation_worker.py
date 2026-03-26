import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any
import sys

from aiokafka import AIOKafkaConsumer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hse_backend.ml_models.model import load_model
from hse_backend.services.predict_violation import predict_violation
from hse_backend.models.advertisement import Advertisement
from hse_backend.clients.kafka import KafkaProducer
from hse_backend.repositories.prediction_cache import PredictionCacheStorage
from hse_backend.repositories.ads import AdRepository
from hse_backend.repositories.moderation import ModerationRepository

MAX_RETRIES = 3
RETRY_DELAY = 5

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
MODERATION_TOPIC = "moderation"
DLQ_TOPIC = "moderation_dlq"
BASE_DIR = Path(__file__).resolve().parent.parent


class ModerationWorker:
    def __init__(self, model_path: Path):
        self.model = load_model(model_path)
        self.kafka_producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        self.cache_storage = PredictionCacheStorage()
        self.ad_repo = AdRepository()
        self.moderation_repo = ModerationRepository()

    async def start(self):
        await self.kafka_producer.start()

    async def stop(self):
        await self.kafka_producer.stop()

    async def process_message_with_retry(
        self, message_data: Dict[str, Any], retry_count: int = 0
    ) -> bool:
        item_id = message_data["item_id"]

        try:
            # получаем данные объявления и продавца через репозиторий
            ad_data = await self.ad_repo.get_ad_with_seller(item_id)
            if not ad_data:
                raise ValueError(f"Ad with item_id = {item_id} not found")

            # проверяем, что для данного item_id есть ожидающая задача модерации
            mod_record = await self.moderation_repo.get_pending_by_item_id(item_id)
            if not mod_record:
                raise ValueError(f"No pending task for item_id = {item_id}")

            task_id = mod_record["id"]

            # создаем модель объявления и делаем предсказание
            ad_model = Advertisement(**ad_data)
            result = predict_violation(self.model, ad_model)

            # кэшируем результат предсказания
            await self.cache_storage.set_prediction_cache(item_id, result)

            # обновляем статус задачи модерации с результатами через репозиторий
            await self.moderation_repo.update_completed(
                task_id, result["is_violation"], result["probability"]
            )
            return True

        except Exception as e:
            error_msg = str(e)
            if retry_count < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                return await self.process_message_with_retry(
                    message_data, retry_count + 1
                )
            else:
                # обновляем статус задачи модерации как failed через репозиторий и отправляем в DLQ
                await self.moderation_repo.update_failed(item_id, error_msg)
                await self.send_to_dlq(message_data, error_msg, retry_count + 1)
                return False

    # отправляем сообщение в DLQ с информацией об ошибке и количестве попыток
    async def send_to_dlq(self, original_message: dict, error: str, retry_count: int):
        dlq_message = {
            "original_message": original_message,
            "error": error,
            "timestamp": datetime.now(),
            "retry_count": retry_count,
        }
        await self.kafka_producer.send_json(DLQ_TOPIC, dlq_message)


async def main():
    model_path = BASE_DIR / "ml_models" / "model.pkl"
    if not model_path.exists():
        print("Model file not found")
        return

    # Initialize database pool
    from hse_backend.clients.postgres import init_pool, close_pool

    await init_pool()

    worker = ModerationWorker(model_path)
    await worker.start()

    consumer = AIOKafkaConsumer(
        MODERATION_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="moderation-group",
        auto_offset_reset="earliest",
        security_protocol="PLAINTEXT",
    )

    await consumer.start()

    try:
        async for msg in consumer:
            print(f"Received raw message: {msg.value}")
            try:
                message_data = json.loads(msg.value.decode("utf-8"))
                print(f"Parsed: {message_data}")
                await worker.process_message_with_retry(message_data, retry_count=0)
            except json.JSONDecodeError as e:
                raw_msg = {"raw": msg.value.decode("utf-8", errors="ignore")}
                await worker.send_to_dlq(
                    raw_msg, f"JSON decode error: {e}", retry_count=0
                )
            except Exception as e:
                print(f"Error processing message: {e}")
                raw_msg = {"raw": msg.value.decode("utf-8", errors="ignore")}
                await worker.send_to_dlq(raw_msg, str(e), retry_count=0)
    finally:
        await consumer.stop()
        await worker.stop()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
