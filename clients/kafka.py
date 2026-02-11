import json
from datetime import datetime
from aiokafka import AIOKafkaProducer


class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self._bootstrap = bootstrap_servers
        self._producer = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_json(self, topic: str, payload: dict) -> None:
        assert self._producer is not None, "Producer not started"
        data = json.dumps(payload, default=str).encode("utf-8")
        await self._producer.send_and_wait(topic, data)

    async def send_moderation_request(self, item_id: int) -> None:
        message = {"item_id": item_id, "timestamp": datetime.now()}
        await self.send_json(topic="moderation", payload=message)
