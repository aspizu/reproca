"""Sessions management for reproca applications."""

from __future__ import annotations

__all__ = ["Sessions"]

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from .memcache import Memcache


class Session[T, U](msgspec.Struct):
    userid: T
    user: U
    created: datetime


class Sessions[T, U]:
    def __init__(self, memcache: Memcache, expire: int = 2592000) -> None:
        """Initialize a sessions manager (Implemented using memcached).

        Args:
        ----
            memcache: The memcache client.
            expire: The expiration time of a session in seconds.

        """
        self.memcache = memcache
        self.expire = expire

    def create(self, userid: T, user: U) -> str:
        """Create a session for user by user id.

        Usage:
        >>> credentials.set_session(reproca.sessions.create(...))
        """
        self.remove_by_userid(userid)
        sessionid = secrets.token_urlsafe()
        self.memcache.set(
            f"sessionid={sessionid}",
            Session(userid, user, datetime.now(tz=UTC)),
            expire=self.expire,
        )
        self.memcache.set(f"userid={userid}", sessionid)
        return sessionid

    def update_by_sessionid(self, sessionid: str, user: U) -> None:
        """Update a session by session id."""
        session: Session[T, U] | None = self.memcache.get(f"sessionid={sessionid}")
        if session is None:
            return
        self.memcache.replace(
            f"sessionid={sessionid}",
            Session(session.userid, user, session.created),
            expire=int(
                self.expire - (datetime.now(tz=UTC) - session.created).total_seconds()
            ),
        )

    def remove_by_userid(self, userid: T) -> None:
        """Remove a session by user id."""
        sessionid: str | None = self.memcache.get(f"userid={userid}")
        if sessionid is None:
            return
        self.memcache.delete_many((f"sessionid={sessionid}", f"userid={userid}"))

    def remove_by_sessionid(self, sessionid: str) -> None:
        """Remove a session by session id."""
        session: Session[T, U] | None = self.memcache.get(f"sessionid={sessionid}")
        if session is None:
            return
        self.memcache.delete_many(
            (f"sessionid={sessionid}", f"userid={session.userid}")
        )

    def get_by_userid[D](self, userid: T, default: D = None) -> U | D:
        """Get user by user id, return default if not found."""
        sessionid: str | None = self.memcache.get(f"userid={userid}")
        if sessionid is None:
            return default
        session: Session[T, U] | None = self.memcache.get(f"sessionid={sessionid}")
        if session is None:
            return default
        return session.user

    def get_by_sessionid[D](self, sessionid: str, default: D = None) -> U | D:
        """Get user by session id, return default if not found."""
        session: Session[T, U] | None = self.memcache.get(f"sessionid={sessionid}")
        if session is None:
            return default
        return session.user
