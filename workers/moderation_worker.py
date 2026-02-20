import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiokafka import AIOKafkaConsumer
from clients.postgres import get_pg_connection
from ml_models.model import load_model
from services.predict_violation import predict_violation
from models.advertisement import Advertisement
from clients.kafka import KafkaProducer
from repositories.prediction_cache import PredictionCacheStorage

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

    async def start(self):
        await self.kafka_producer.start()

    async def stop(self):
        await self.kafka_producer.stop()

    async def process_message_with_retry(
        self, message_data: Dict[str, Any], retry_count: int = 0
    ) -> bool:
        item_id = message_data["item_id"]

        try:
            async with get_pg_connection() as conn:
                ad_row = await conn.fetchrow(
                    """
                    SELECT 
                        a.item_id,
                        a.seller_id,
                        u.is_verified AS is_verified_seller,
                        a.name,
                        a.description,
                        a.category,
                        a.images_qty
                    FROM ads a
                    JOIN users u ON a.seller_id = u.id
                    WHERE a.item_id = $1
                    """,
                    item_id,
                )
                if not ad_row:
                    raise ValueError(f"Ad with item_id = {item_id} not found")

                mod_row = await conn.fetchrow(
                    """
                    SELECT id FROM moderation_results 
                    WHERE item_id = $1 AND status = 'pending'
                    """,
                    item_id,
                )
                if not mod_row:
                    raise ValueError(f"No pending task for item_id = {item_id}")

                task_id = mod_row["id"]

            ad_model = Advertisement(**dict(ad_row))
            result = predict_violation(self.model, ad_model)

            await self.cache_storage.set_prediction_cache(item_id, result)

            async with get_pg_connection() as conn:
                await conn.execute(
                    """
                    UPDATE moderation_results
                    SET status = 'completed',
                        is_violation = $1,
                        probability = $2,
                        processed_at = NOW()
                    WHERE id = $3
                    """,
                    result["is_violation"],
                    result["probability"],
                    task_id,
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
                async with get_pg_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE moderation_results
                        SET status = 'failed',
                            error_message = $1,
                            processed_at = NOW()
                        WHERE item_id = $2 AND status = 'pending'
                        """,
                        error_msg,
                        item_id,
                    )
                await self.send_to_dlq(message_data, error_msg, retry_count + 1)
                return False

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


if __name__ == "__main__":
    asyncio.run(main())
