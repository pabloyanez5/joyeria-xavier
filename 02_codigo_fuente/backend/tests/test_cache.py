import redis

from app.cache import CacheIdentidad


def test_guarda_y_obtiene_id(cache):
    cache.guardar("whatsapp", "593999111222", 7)
    assert cache.obtener("whatsapp", "593999111222") == 7


def test_obtener_inexistente_devuelve_none(cache):
    assert cache.obtener("whatsapp", "no-existe") is None


def test_la_clave_expira(cache):
    cache.guardar("whatsapp", "593999111222", 7)
    ttl = cache.redis.ttl("cliente:whatsapp:593999111222")
    assert 0 < ttl <= 24 * 60 * 60


class RedisCaido:
    def get(self, *args, **kwargs):
        raise redis.ConnectionError("caído")

    def set(self, *args, **kwargs):
        raise redis.ConnectionError("caído")


def test_si_redis_cae_no_rompe():
    cache = CacheIdentidad(RedisCaido())
    assert cache.obtener("whatsapp", "1") is None
    cache.guardar("whatsapp", "1", 1)  # no debe lanzar error