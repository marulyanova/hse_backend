import logging
import json
from typing import Optional, Dict, Any

from clients.redis import redis_client


class PredictionCacheStorage:
    CACHE_TTL_SECONDS = 3600
    CACHE_KEY_PREFIX = "prediction"

    def _make_key(self, item_id: int) -> str:
        return f"{self.CACHE_KEY_PREFIX}:{item_id}"

    async def get_prediction_cache(self, item_id: int) -> Optional[Dict[str, Any]]:
        key = self._make_key(item_id)
        value = await redis_client.get(key)

        if value is None:
            return None

        if isinstance(value, dict):
            return value

        try:
            result = json.loads(value)
            return result
        except (json.JSONDecodeError, TypeError) as e:
            return None

    async def set_prediction_cache(
        self,
        item_id: int,
        prediction: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:

        # сохранение кэша по ключу с TTL
        key = self._make_key(item_id)
        ttl = ttl_seconds if ttl_seconds is not None else self.CACHE_TTL_SECONDS

        try:
            success = await redis_client.set(key, prediction, ttl_seconds=ttl)
            return success
        except Exception as e:
            return False

    async def delete_prediction_cache(self, item_id: int) -> bool:
        key = self._make_key(item_id)
        result = await redis_client.delete(key)
        return result
