from __future__ import annotations

__all__ = ["Response"]

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime


class Response:
    def __init__(self) -> None:
        self.cookies: list[
            tuple[
                str,
                str,
                int | None,
                datetime | str | int | None,
                str,
                str | None,
                bool,
                bool,
                Literal["lax", "strict", "none"],
            ]
        ] = []
        self.headers: dict[str, str] = {}

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
        self.cookies.append(
            (
                key,
                value,
                max_age,
                expires,
                path,
                domain,
                secure,
                httponly,
                samesite,
            )
        )

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
