from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import msgspec
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import PlainTextResponse, Response
from starlette.routing import BaseRoute, Route

from ._state import _methods, _routes, _sessions
from .codegen import generate_typescript_bindings
from .introspection import Parameters, get_parameters
from .protocol import parse_parameters
from .sessions import Sessions

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.types import ExceptionHandler, Lifespan

    from .sessions import Sessions

__all__ = [
    "create_starlette_application",
    "generate_typescript_bindings",
    "method",
]


type Method = Callable[..., Awaitable[object]]


def create_starlette_application(
    sessions: Sessions[Any],
    debug: bool = False,
    routes: list[BaseRoute] | None = None,
    middleware: Sequence[Middleware] | None = None,
    exception_handlers: Mapping[Any, ExceptionHandler] | None = None,
    on_startup: Sequence[Callable[[], Any]] | None = None,
    on_shutdown: Sequence[Callable[[], Any]] | None = None,
    lifespan: Lifespan[Starlette] | None = None,
    base: str | None = None,
) -> Starlette:
    global _sessions  # noqa: PLW0603
    if base:
        if base[0] != "/":
            base = "/" + base
        if base[-1] == "/":
            base = base[:-1]
        for route in _routes:
            route.path = base + route.path
    _sessions = sessions
    allroutes: Sequence[BaseRoute] = [*routes, *_routes] if routes else _routes
    return Starlette(
        routes=allroutes,
        debug=debug,
        middleware=middleware,
        exception_handlers=exception_handlers,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        lifespan=lifespan,
    )


def method(method: Method) -> Method:
    parameters = get_parameters(method)

    method.__parameters_type__ = parameters.decoder.type  # pyright: ignore[reportFunctionMemberAccess]
    _methods.append(method)

    class Endpoint(HTTPEndpoint):
        async def post(self, request: Request) -> Response:
            return await invoke_method(method, request, parameters)

    route = Route(f"/{method.__name__.replace('_', '-')}", Endpoint)
    _routes.append(route)

    return method


async def invoke_method(
    method: Method, request: Request, parameters: Parameters
) -> Response:
    try:
        struct = await parse_parameters(request, parameters)
    except msgspec.ValidationError as error:
        return PlainTextResponse(str(error), HTTPStatus.BAD_REQUEST)
    kwargs = {
        parameter.name: getattr(struct, parameter.name)
        for parameter in parameters.entries.values()
    }
    if parameters.needs_request:
        kwargs["request"] = request
    if parameters.needs_session:
        kwargs["session"] = None
    assert _sessions is not None
    if session := _sessions.get(request.cookies.get("session-id")):
        if parameters.needs_session:
            kwargs["session"] = session
    elif parameters.session_mandatory:
        return PlainTextResponse("Unauthorized.", HTTPStatus.UNAUTHORIZED)

    response = await method(**kwargs)
    if isinstance(response, Response):
        return response
    return Response(msgspec.json.encode(response), media_type="application/json")
