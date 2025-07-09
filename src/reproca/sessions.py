from __future__ import annotations

import secrets
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.responses import Response


class Sessions[T]:
    expiry: float = 2592000
    "Session expiry in seconds."

    def __init__(self) -> None:
        self._users: dict[str, str] = {}
        self._sessions: dict[str, tuple[str, T]] = {}
        self._expiry: dict[str, float] = {}

    def get(self, session_id: str | None) -> tuple[str, T] | None:
        if session_id not in self._sessions:
            return None
        user, obj = self._sessions[session_id]
        expiry = self._expiry[session_id]
        if time() > expiry:
            del self._users[user]
            del self._sessions[session_id]
            del self._expiry[session_id]
            return None
        return user, obj

    def create(self, user: str, obj: T) -> str:
        if session_id := self._users.get(user):
            del self._sessions[session_id]
            del self._expiry[session_id]
        session_id = secrets.token_urlsafe()
        self._users[user] = session_id
        self._sessions[session_id] = (user, obj)
        self._expiry[session_id] = time() + self.expiry
        return session_id

    def create_session_cookie(self, user: str, obj: T, response: Response) -> Response:
        session_id = self.create(user, obj)
        response.set_cookie(
            "cookie-id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=int(self.expiry),
        )
        return response
