from __future__ import annotations

from errno import EFAULT
from http import HTTPStatus
from inspect import signature
from typing import TYPE_CHECKING, Any, get_type_hints

import msgspec
from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from typing_extensions import Sentinel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request

_routes = []

type Method = Callable[..., Awaitable[object]]


def create_starlette_application(*args, **kwargs) -> Starlette:
    return Starlette(*args, **kwargs, routes=_routes)


def method(method: Method) -> Method:
    parameters = get_parameters(method)

    class Endpoint(HTTPEndpoint):
        async def get(self, request: Request) -> Response:
            return await get_method_help(method, parameters)

        async def post(self, request: Request) -> Response:
            return await invoke_method(method, request, parameters)

    route = Route(f"/{method.__name__.replace('_', '-')}", Endpoint)
    _routes.append(route)

    return method


def convert_case(text: str) -> str:
    return text.lower().replace("-", "_")


def collapse_case(_type: type, obj: Any) -> Any:
    if isinstance(obj, dict):
        return {convert_case(key): value for key, value in obj.items()}
    return obj


NODEFAULT = Sentinel("NODEFAULT")
SPECIAL_PARAMETERS = ["return", "session", "request"]


class Parameter(msgspec.Struct):
    name: str
    type: object
    default: object


class Parameters(msgspec.Struct):
    entries: dict[str, Parameter]
    decoder: msgspec.json.Decoder[msgspec.Struct]
    needs_request: bool


def get_parameters(func: Callable[..., object]) -> Parameters:
    entries = {}
    type_hints = get_type_hints(func)
    for key, value in signature(func).parameters.items():
        if key in SPECIAL_PARAMETERS:
            continue
        default = NODEFAULT if value.default is value.empty else value.default
        entries[key.lower()] = Parameter(key, type_hints[key], default)

    fields = []
    for parameter in entries.values():
        if parameter.default is NODEFAULT:
            fields.append((parameter.name, parameter.type))
        else:
            fields.append((parameter.name, parameter.type, parameter.default))
    decoder = msgspec.json.Decoder(msgspec.defstruct("X", fields))

    return Parameters(entries, decoder, needs_request="request" in type_hints)


def parse_parameter(text: str, type_: object) -> object:
    if isinstance(type_, type) and issubclass(type_, str):
        return text
    return msgspec.json.decode(text, type=type_, dec_hook=collapse_case)


async def parse_parameters(request: Request, parameters: Parameters) -> msgspec.Struct:
    effective = {}

    for key, value in request.query_params.items():
        parameter = parameters.entries.get(convert_case(key))
        if parameter is None:
            continue
        effective[parameter.name] = parse_parameter(value, parameter.type)

    for key, value in request.headers.items():
        key = key.lower()  # noqa: PLW2901
        if not key.startswith("x-"):
            continue
        parameter = parameters.entries.get(convert_case(key.removeprefix("x-")))
        if parameter is None:
            continue
        effective[parameter.name] = parse_parameter(value, parameter.type)

    body = msgspec.json.decode(
        await request.body() or b"{}", type=dict[str, Any], dec_hook=collapse_case
    )

    round_trip = msgspec.json.encode({**effective, **body})
    return parameters.decoder.decode(round_trip)


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
    response = await method(**kwargs)
    if isinstance(response, Response):
        return response
    return Response(msgspec.json.encode(response), media_type="application/json")


def _format_method_info(method: Method) -> str:
    method_name = method.__name__.replace("_", "-")
    text = f"Method: {method_name}\n"
    text += f"Endpoint: /{method_name}\n\n"

    if method.__doc__:
        text += f"Description:\n{method.__doc__.strip()}\n\n"

    return text


def _format_parameters(parameters: Parameters) -> str:
    if not parameters.entries:
        return ""

    text = "Parameters:\n"
    for param in parameters.entries.values():
        param_type = getattr(param.type, "__name__", str(param.type))
        if param.default is not NODEFAULT:
            text += (
                f"  {param.name} ({param_type}, optional, default: {param.default})\n"
            )
        else:
            text += f"  {param.name} ({param_type}, required)\n"
    return text + "\n"


def _get_example_value(param: Parameter) -> str:
    if param.default is not NODEFAULT:
        return (
            f'"{param.default}"'
            if isinstance(param.default, str)
            else str(param.default)
        )

    param_type = getattr(param.type, "__name__", str(param.type))
    type_examples = {
        "str": '"example"',
        "string": '"example"',
        "int": "42",
        "integer": "42",
        "float": "3.14",
        "number": "3.14",
        "bool": "true",
        "boolean": "true",
    }
    return type_examples.get(param_type, '"value"')


def _format_usage_example(method: Method, parameters: Parameters) -> str:
    method_name = method.__name__.replace("_", "-")
    text = "Usage:\n"
    text += f"POST /{method_name}\n"
    text += "Content-Type: application/json\n\n"

    if parameters.entries:
        text += "Example request body:\n"
        text += "{\n"
        param_items = list(parameters.entries.values())
        for i, param in enumerate(param_items):
            comma = "," if i < len(param_items) - 1 else ""
            example_value = _get_example_value(param)
            text += f'  "{param.name}": {example_value}{comma}\n'
        text += "}\n\n"

    text += "Parameters can also be passed via:\n"
    text += "- Query parameters: ?param=value\n"
    text += "- Headers: X-Param: value\n"

    return text


async def get_method_help(method: Method, parameters: Parameters) -> Response:
    text = _format_method_info(method)
    text += _format_parameters(parameters)
    text += _format_usage_example(method, parameters)

    return PlainTextResponse(text)
