# ruff: noqa: PLW2901

from __future__ import annotations

from http import HTTPStatus
from inspect import signature
from types import UnionType
from typing import TYPE_CHECKING, Any, final, get_origin, get_type_hints

import msgspec
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.requests import Request

methods: list[type] = []

SPECIAL_PARAMETERS = ["return", "session", "request"]


def jsoncast(text: str, expected: type) -> Any:
    if expected is str:
        return text
    return msgspec.json.decode(text)


def method[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    type_hints = get_type_hints(func)
    sig = signature(func).parameters
    parameter_fields = [
        (key, type_hints[value.name])
        if value.default is value.empty
        else (key, type_hints[value.name], value.default)
        for key, value in sig.items()
        if key not in SPECIAL_PARAMETERS
    ]
    parameter_keys = {key.lower(): (key, type_) for key, type_, *_ in parameter_fields}
    decoder = msgspec.json.Decoder(msgspec.defstruct(func.__name__, parameter_fields))
    parameter_session_optional = False
    if (obj := type_hints.get("session")) and get_origin(obj) is UnionType:
        parameter_session_optional = True

    @final
    class Method(HTTPEndpoint):
        implementation = func

        async def get(self, request: Request) -> Response:
            return PlainTextResponse(func.__doc__)

        async def post(self, request: Request) -> Response:
            body = {}
            try:
                body = msgspec.json.decode(
                    await request.body(),
                    type=dict[str, Any],
                )
            except msgspec.ValidationError as error:
                return PlainTextResponse(str(error), status_code=HTTPStatus.BAD_REQUEST)
            except msgspec.DecodeError:
                pass
            parameters = {}
            for key, value in request.headers.items():
                key = key.lower()
                if key.startswith("x-"):
                    key = key.removeprefix("x-")
                    if key in parameter_keys:
                        parameters[parameter_keys[key][0]] = jsoncast(
                            value, parameter_keys[key][1]
                        )
            for key, value in request.query_params.items():
                key = key.lower()
                if key in parameter_keys:
                    parameters[parameter_keys[key][0]] = jsoncast(
                        value, parameter_keys[key][1]
                    )
            round_trip = msgspec.json.encode({**body, **parameters})
            try:
                obj = decoder.decode(round_trip)
                kwargs = {key: getattr(obj, key) for key, _ in parameter_keys.values()}
            except msgspec.ValidationError as error:
                return PlainTextResponse(str(error), status_code=HTTPStatus.BAD_REQUEST)
            if "request" in sig:
                kwargs["request"] = request
            response_data = await func(**kwargs)  # pyright: ignore[reportCallIssue, reportGeneralTypeIssues]
            if isinstance(response_data, Response):
                return response_data
            return JSONResponse(response_data)

    methods.append(Method)
    return func


def create_starlette_application() -> Starlette:
    return Starlette(
        routes=[
            Route(path=f"/{method.implementation.__name__}", endpoint=method)
            for method in methods
        ]
    )
