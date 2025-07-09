from __future__ import annotations

from inspect import signature
from types import UnionType
from typing import TYPE_CHECKING, get_origin, get_type_hints

import msgspec
from typing_extensions import Sentinel

if TYPE_CHECKING:
    from collections.abc import Callable

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
    needs_session: bool
    session_mandatory: bool


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

    session_mandatory = False
    if annotation := type_hints.get("session"):
        session_mandatory = get_origin(annotation) is UnionType

    return Parameters(
        entries,
        decoder,
        "request" in type_hints,
        "session" in type_hints,
        session_mandatory,
    )
