import os
from functools import lru_cache

import redis

TTL_SEGUNDOS = 24 * 60 * 60


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_redis_url(), decode_responses=True)


class CacheIdentidad:
    """Guarda (canal, id_canal) -> id del cliente. Si Redis falla, no rompe nada."""

    def __init__(self, cliente_redis, ttl: int = TTL_SEGUNDOS):
        self.redis = cliente_redis
        self.ttl = ttl

    @staticmethod
    def _clave(canal: str, id_canal: str) -> str:
        return f"cliente:{canal}:{id_canal}"

    def obtener(self, canal: str, id_canal: str) -> int | None:
        try:
            valor = self.redis.get(self._clave(canal, id_canal))
        except redis.RedisError:
            return None
        return int(valor) if valor is not None else None

    def guardar(self, canal: str, id_canal: str, cliente_id: int) -> None:
        try:
            self.redis.set(self._clave(canal, id_canal), cliente_id, ex=self.ttl)
        except redis.RedisError:
            pass


def get_cache() -> CacheIdentidad:
    return CacheIdentidad(get_redis())