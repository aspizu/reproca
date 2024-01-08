from __future__ import annotations

__all__ = ["SESSION_VALID_FOR_DAYS", "Sessions"]

import secrets
from datetime import datetime
from typing import Generic, TypeVar
from msgspec import Struct
from warnings import warn

T = TypeVar("T")
U = TypeVar("U")
D = TypeVar("D")

SESSION_VALID_FOR_DAYS = 15


class Session(Struct, Generic[T, U]):
    userid: T
    user: U
    created: datetime

    def is_expired(self) -> bool:
        return (datetime.now() - self.created).days > SESSION_VALID_FOR_DAYS


class Sessions(Generic[T, U]):
    def __init__(self) -> None:
        self.sessions: dict[str, Session[T, U]] = {}
        self.users: dict[T, str] = {}

    def create(self, userid: T, user: U) -> str:
        self.remove_by_userid(userid)
        sessionid = secrets.token_urlsafe()
        self.users[userid] = sessionid
        self.sessions[sessionid] = Session(userid, user, datetime.now())
        return sessionid

    def remove_by_userid(self, userid: T) -> None:
        try:
            sessionid = self.users.pop(userid)
            self.sessions.pop(sessionid)

        except KeyError:
            warn(f"User ID {userid!r} was already removed")

    def remove_by_sessionid(self, sessionid: str) -> None:
        try:
            session = self.sessions.pop(sessionid)
            self.users.pop(session.userid)

        except KeyError:
            warn(f"Session ID {sessionid!r} was already removed")

    def get_by_userid(self, userid: T, default: D = None) -> D | U:
        if sessionid := self.users.get(userid):
            if session := self.sessions.get(sessionid):
                return session.user

        return default

    def get_by_sessionid(self, sessionid: str, default: D = None) -> D | U:
        if session := self.sessions.get(sessionid):
            return session.user

        return default
