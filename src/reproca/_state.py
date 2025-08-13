from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.routing import Route

    from . import Method
    from .sessions import Sessions

_routes: list[Route] = []
_sessions: Sessions[Any] | None = None
_methods: list[Method] = []
