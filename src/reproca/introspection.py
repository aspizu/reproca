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
    hints = get_type_hints(func)
    for key, value in signature(func).parameters.items():
        if key in SPECIAL_PARAMETERS:
            continue
        default = NODEFAULT if value.default is value.empty else value.default
        entries[key.lower()] = Parameter(key, hints[key], default)
    fields = []
    for p in entries.values():
        if p.default is NODEFAULT:
            fields.append((p.name, p.type))
        else:
            fields.append((p.name, p.type, p.default))
    name = "".join(part.capitalize() for part in func.__name__.split("_"))
    decoder = msgspec.json.Decoder(msgspec.defstruct(f"{name}Parameters", fields))
    ann = hints.get("session")
    mandatory = get_origin(ann) is not UnionType if ann else False
    return Parameters(
        entries, decoder, "request" in hints, "session" in hints, mandatory
    )
