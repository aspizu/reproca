from __future__ import annotations

import subprocess
import sys
import typing
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
)
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from platform import python_version_tuple
from types import NoneType, UnionType, get_original_bases
from typing import (
    IO,
    Any,
    Generic,
    Literal,
    TypeAliasType,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import msgspec

from .introspection import SPECIAL_PARAMETERS
from .state import _methods


def get_type_alias_value(obj: TypeAliasType) -> object:
    if python_version_tuple() >= ("3", "12"):
        return obj.__value__
    module_name = getattr(obj, "__module__", None)
    if module_name is None:
        globalns = {}
    else:
        module = sys.modules.get(module_name)
        globalns = getattr(module, "__dict__", {}) if module else {}
    localns = dict(vars(obj))
    return typing._eval_type(obj.__value__, globalns, localns)  # pyright: ignore[reportAttributeAccessIssue]  # noqa: SLF001


@dataclass
class WriterState:
    file: IO[str]


def write(state: WriterState, *strings: str) -> None:
    state.file.writelines(strings)


def intersperse(
    separator: Callable[[], None], funcs: Iterable[Callable[[], None]]
) -> None:
    it = iter(funcs)
    func = next(it, None)
    while func is not None:
        func()
        func = next(it, None)
        if func is not None:
            separator()


def generate_typescript_bindings(
    output_path: Path | str = "api.gen.ts",
) -> None:
    if isinstance(output_path, str):
        output_path = Path(output_path)

    with output_path.open("w", encoding="utf-8") as f:
        writer = WriterState(f)
        state = CodegenState(writer)
        for m in _methods:
            method(state, m)
        resolve(state)
    try:
        subprocess.run(  # noqa: S603
            ["npx", "prettier@latest", "-uwu", str(output_path)],  # noqa: S607
            check=True,
        )
    except FileNotFoundError:
        pass
    except subprocess.CalledProcessError:
        pass


# Remove api_prefix from CodegenState
@dataclass
class CodegenState:
    writer: WriterState
    unresolved: set[type[Enum | msgspec.Struct] | TypeAliasType] = field(
        default_factory=set
    )
    resolved: set[object] = field(default_factory=set)
    call_api_emitted: bool = False


# Always emit 'export let apiPrefix = "/";' at the top, and use it in callApi


def emit_call_api(state: CodegenState) -> None:
    if state.call_api_emitted:
        return
    write(
        state.writer,
        'export let apiPrefix = "/";\n',
        "async function callApi<T>(name: string, parameters: any): Promise<T> {\n",
        "  const response = await fetch(`${apiPrefix}${name}`, {\n",
        "    method: 'POST',\n",
        "    headers: { 'Content-Type': 'application/json' },\n",
        "    body: JSON.stringify(parameters),\n",
        "    credentials: 'include',\n",
        "  });\n",
        "  if (!response.ok) throw new Error(await response.text());\n",
        "  return await response.json();\n",
        "}\n\n",
    )
    state.call_api_emitted = True


def resolve(state: CodegenState) -> None:
    if len(state.unresolved) == 0:
        return
    state.resolved.update(state.unresolved)
    unresolved = state.unresolved
    state.unresolved = set()
    for obj in unresolved:
        if isinstance(obj, TypeAliasType):
            type_alias(state, obj)
        elif issubclass(obj, Enum):
            enum(state, obj)
        else:
            msgspec_struct(state, obj)
    resolve(state)


def enum(state: CodegenState, obj: type[Enum]) -> None:
    doc(state, obj.__doc__)
    write(state.writer, "export enum ", obj.__name__, "{")
    for member in obj:
        write(state.writer, member.name, "=")
        literal(state, member.value)
        write(state.writer, ",")
    write(state.writer, "}")


def type_alias(state: CodegenState, obj: TypeAliasType) -> None:
    write(state.writer, "export type ", obj.__name__)
    if obj.__type_params__:
        write(state.writer, "<")
        intersperse(
            lambda: write(state.writer, ","),
            [lambda p=param: type_object(state, p) for param in obj.__type_params__],
        )
        write(state.writer, ">")
    write(state.writer, "=")
    type_object(state, get_type_alias_value(obj))
    write(state.writer, ";")


def literal(state: CodegenState, obj: object) -> None:
    match obj:
        case None:
            write(state.writer, "null")
        case True:
            write(state.writer, "true")
        case False:
            write(state.writer, "false")
        case int() | float() | str():
            write(state.writer, repr(obj))
        case _:
            msg = f"Unsupported literal type: {obj!r}"
            raise TypeError(msg)


def type_object(state: CodegenState, type_obj: object) -> None:  # noqa: C901, PLR0912
    match type_obj:
        case type() if issubclass(type_obj, Enum):
            if type_obj not in state.resolved:
                state.unresolved.add(type_obj)
            write(state.writer, type_obj.__name__)
        case msgspec.UnsetType():
            write(state.writer, "undefined")
        case type() if issubclass(type_obj, NoneType):
            write(state.writer, "null")
        case None:
            write(state.writer, "null")
        case type() if issubclass(type_obj, bool):
            write(state.writer, "boolean")
        case type() if issubclass(type_obj, (int, float)):
            write(state.writer, "number")
        case type() if issubclass(type_obj, (str, bytes, bytearray, datetime)):
            write(state.writer, "string")
        case type() if issubclass(type_obj, msgspec.Struct):
            if type_obj not in state.resolved:
                state.unresolved.add(type_obj)
            write(state.writer, type_obj.__name__)
        case type() if type_obj is msgspec.UnsetType:
            write(state.writer, "undefined")
        case TypeVar():
            write(state.writer, type_obj.__name__)
        case TypeAliasType():
            if type_obj not in state.resolved:
                state.unresolved.add(type_obj)
            write(state.writer, type_obj.__name__)
        case type() if type_obj is Any:
            write(state.writer, "any")
        case _:
            generic_type(state, type_obj)


def generic_type(state: CodegenState, type_obj: object) -> None:  # noqa: C901
    orig = get_origin(type_obj)
    match orig:
        case TypeAliasType():
            args = get_args(type_obj)
            if orig not in state.resolved:
                state.unresolved.add(orig)
            write(state.writer, orig.__name__)
            write(state.writer, "<")
            intersperse(
                lambda: write(state.writer, ","),
                [lambda a=arg: type_object(state, a) for arg in args],
            )
            write(state.writer, ">")
        case type() if issubclass(orig, msgspec.Struct):
            args = get_args(type_obj)
            if orig not in state.resolved:
                state.unresolved.add(orig)
            write(state.writer, orig.__name__)
            write(state.writer, "<")
            intersperse(
                lambda: write(state.writer, ","),
                [lambda a=arg: type_object(state, a) for arg in args],
            )
            write(state.writer, ">")
        case type() if issubclass(orig, tuple):
            args = get_args(type_obj)
            if args[1:] == (...,):
                type_object(state, list[args[0]])
                return
            write(state.writer, "[")
            intersperse(
                lambda: write(state.writer, ","),
                [lambda a=arg: type_object(state, a) for arg in args],
            )
            write(state.writer, "]")
        case type() if issubclass(orig, (dict, Mapping, MutableMapping)):
            args = get_args(type_obj)
            write(state.writer, "Record<")
            type_object(state, args[0])
            write(state.writer, ", ")
            type_object(state, args[1])
            write(state.writer, ">")
        case type() if issubclass(
            orig,
            (list, set, frozenset, Collection, Sequence, MutableSequence, MutableSet),
        ):
            write(state.writer, "(")
            type_object(state, get_args(type_obj)[0])
            write(state.writer, ")[]")
        case orig if orig is Literal:
            intersperse(
                lambda: write(state.writer, "|"),
                [lambda a=arg: literal(state, a) for arg in get_args(type_obj)],
            )
        case _ if orig is UnionType or orig is Union:

            def do(arg: object) -> None:
                write(state.writer, "(")
                type_object(state, arg)
                write(state.writer, ")")

            write(state.writer, "(")
            intersperse(
                lambda: write(state.writer, "|"),
                [lambda a=arg: do(a) for arg in get_args(type_obj)],
            )
            write(state.writer, ")")
        case _:
            msg = f"Could not convert type: {type_obj!r}, origin: {orig!r}"
            raise TypeError(msg)


def doc(state: CodegenState, docstr: str | None) -> None:
    if docstr:
        write(state.writer, f"/** {docstr} */\n")


def msgspec_struct(state: CodegenState, struct: type[msgspec.Struct]) -> None:
    doc(state, struct.__doc__)
    write(state.writer, "export interface ", struct.__name__)
    if params := next(
        (
            get_args(base)
            for base in get_original_bases(struct)
            if get_origin(base) is Generic
        ),
        None,
    ):
        write(state.writer, "<")
        intersperse(
            lambda: write(state.writer, ","),
            [lambda p=param: type_object(state, p) for param in params],
        )
        write(state.writer, ">")
    write(state.writer, "{")
    for fieldname, fieldtype in get_type_hints(struct).items():
        optional = False
        if (
            get_origin(fieldtype) is UnionType or get_origin(fieldtype) is Union
        ) and msgspec.UnsetType in (args := get_args(fieldtype)):
            args = (arg for arg in args if arg is not msgspec.UnsetType)
            fieldtype = Union[*args]  # noqa: PLW2901
            optional = True
        write(state.writer, fieldname, ":" if not optional else "?:")
        type_object(state, fieldtype)
        write(state.writer, ";")
    write(state.writer, "}")


def field_with_type(state: CodegenState, name: str, obj: object) -> None:
    write(state.writer, name, ":")
    type_object(state, obj)


def method(state: CodegenState, method: Callable[..., object]) -> None:
    emit_call_api(state)
    doc(state, method.__doc__)
    write(state.writer, "export async function ", method.__name__, "(parameters: ")
    type_hints = get_type_hints(method)
    param_type = getattr(method, "__parameters_type__", None)
    if param_type is not None:
        type_object(state, param_type)
    elif "parameters" in type_hints:
        type_object(state, type_hints["parameters"])
    else:
        write(state.writer, "{}")
    if len([key for key in type_hints if key not in SPECIAL_PARAMETERS]) == 0:
        write(state.writer, " = {}")
    write(state.writer, "):")
    write(state.writer, "Promise<")
    type_object(state, type_hints["return"])
    write(state.writer, ">{\n")
    write(
        state.writer,
        "  return callApi<",
    )
    type_object(state, type_hints["return"])
    write(
        state.writer,
        '>("',
        method.__name__.replace("_", "-"),
        '", parameters);\n',
        "}\n\n",
    )
