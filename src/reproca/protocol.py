from __future__ import annotations

from typing import TYPE_CHECKING, Any

import msgspec

if TYPE_CHECKING:
    from starlette.requests import Request

    from reproca.introspection import Parameters


def convert_case(text: str) -> str:
    return text.lower().replace("-", "_")


def collapse_case(_type: type, obj: Any) -> Any:
    if isinstance(obj, dict):
        return {convert_case(key): value for key, value in obj.items()}
    return obj


def parse_parameter(text: str, type_: object) -> object:
    if isinstance(type_, type) and issubclass(type_, str):
        return text
    return msgspec.json.decode(text, type=type_, dec_hook=collapse_case)


async def parse_parameters(request: Request, parameters: Parameters) -> msgspec.Struct:
    effective = {}
    for key, value in request.query_params.items():
        converted_key = convert_case(key)
        if param := parameters.entries.get(converted_key):
            effective[param.name] = parse_parameter(value, param.type)
    for key, value in request.headers.items():
        key = key.lower()  # noqa: PLW2901
        if not key.startswith("x-"):
            continue
        converted_key = convert_case(key.removeprefix("x-"))
        if param := parameters.entries.get(converted_key):
            effective[param.name] = parse_parameter(value, param.type)
    body = msgspec.json.decode(
        await request.body() or b"{}", type=dict[str, Any], dec_hook=collapse_case
    )
    round_trip = msgspec.json.encode({**effective, **body})
    return parameters.decoder.decode(round_trip)
