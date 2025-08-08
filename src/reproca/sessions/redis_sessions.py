from __future__ import annotations

from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any, cast

from reproca.sessions import Sessions

if TYPE_CHECKING:
    from redis import Redis


class RedisDict(MutableMapping[str, str]):
    def __init__(self, redis: Redis, prefix: str, ex: int | None = None) -> None:
        self.redis = redis
        self.prefix: str = prefix
        self.ex: int | None = ex

    def __getitem__(self, key: str) -> str:
        value = self.redis.get(f"{self.prefix}:{key}")
        if value is None:
            raise KeyError(key)
        return cast("str", value)

    def __setitem__(self, key: str, value: str) -> None:
        self.redis.set(f"{self.prefix}:{key}", value, ex=self.ex)

    def __delitem__(self, key: str) -> None:
        self.redis.delete(f"{self.prefix}:{key}")

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return cast("int", self.redis.exists(f"{self.prefix}:{key}")) > 0

    def __iter__(self) -> Any:
        msg = "Iterating over RedisDict is not supported."
        raise NotImplementedError(msg)

    def __len__(self) -> int:
        msg = "Getting length of RedisDict is not supported."
        raise NotImplementedError(msg)


class RedisSessions[T](Sessions[T]):
    def __init__(self, redis: Redis) -> None:
        super().__init__(
            RedisDict(redis, "reproca.redis_sessions.users", ex=int(self.max_age)),
            RedisDict(redis, "reproca.redis_sessions.sessions", ex=int(self.max_age)),
            RedisDict(redis, "reproca.redis_sessions.expiry", ex=int(self.max_age)),
        )
