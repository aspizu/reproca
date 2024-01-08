from __future__ import annotations

__all__ = ["Response"]

from typing import TYPE_CHECKING, Literal
from dataclasses import dataclass

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class Cookie:
    key: str
    value: str
    max_age: int | None
    expires: datetime | str | int | None
    path: str
    domain: str | None
    secure: bool
    httponly: bool
    samesite: Literal["lax", "strict", "none"]

class Response:
    def __init__(self) -> None:
        self._cookies: list[Cookie] = []
        self._headers: dict[str, str] = {}

    def set_cookie(
        self,
        key: str,
        value: str = "",
        *,
        max_age: int | None = None,
        expires: datetime | str | int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Literal["lax", "strict", "none"] = "lax",
    ) -> None:
        self._cookies.append(Cookie(key, value, max_age, expires, path, domain, secure, httponly, samesite))

    def set_session(self, sessionid: str) -> None:
        self.set_cookie(
            "reproca_session_id",
            sessionid,
            secure=True,
            httponly=True,
            samesite="strict",
        )

    def unset_session(self) -> None:
        self.set_cookie(
            "reproca_session_id",
            "",
            secure=True,
            httponly=True,
            samesite="strict",
        )

    @property
    def cookies(self) -> list[Cookie]:
        return self._cookies

    @property
    def headers(self) -> dict[str, str]:
        return self._headers
