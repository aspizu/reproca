from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.responses import Response

__all__ = ["Sessions"]


@dataclass
class Sessions[T]:
    users: MutableMapping[str, str] = field(default_factory=dict)
    "Mapping of user IDs to session IDs."
    sessions: MutableMapping[str, str] = field(default_factory=dict)
    "Mapping of session IDs to tuples of user ID and session object."
    expiry: MutableMapping[str, str] = field(default_factory=dict)
    "Mapping of session IDs to expiry timestamps."
    max_age: float = 2592000
    "Session expiry in seconds."

    def get(self, session_id: str | None) -> tuple[str, T] | None:
        if session_id is None:
            return None
        if session_id not in self.sessions:
            return None
        user, obj = msgspec.json.decode(self.sessions[session_id])
        max_age = float(self.expiry[session_id])
        if time() > max_age:
            del self.users[user]
            del self.sessions[session_id]
            del self.expiry[session_id]
            return None
        return user, obj

    def create(self, user: str, obj: T) -> str:
        if session_id := self.users.get(user):
            del self.sessions[session_id]
            del self.expiry[session_id]
        session_id = secrets.token_urlsafe()
        self.users[user] = session_id
        self.sessions[session_id] = msgspec.json.encode((user, obj)).decode()
        self.expiry[session_id] = str(time() + self.max_age)
        return session_id

    def create_session_cookie(self, user: str, obj: T, response: Response) -> Response:
        session_id = self.create(user, obj)
        response.set_cookie(
            "session-id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=int(self.max_age),
        )
        return response

    def remove(self, user: str) -> None:
        if session_id := self.users.get(user):
            del self.sessions[session_id]
            del self.expiry[session_id]
            del self.users[user]

    def update(self, user: str, obj: T) -> None:
        session_id = self.users.get(user)
        if session_id is None:
            return
        self.sessions[session_id] = msgspec.json.encode(obj).decode()
