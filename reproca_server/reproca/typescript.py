"""Transpiles Python types to TypeScript types."""
from __future__ import annotations
import hashlib

__all__ = []

import functools
import sys
import typing
from datetime import datetime
from hashlib import sha512
from types import NoneType, UnionType
from typing import (
    IO,
    TYPE_CHECKING,
    Callable,
    Collection,
    Generic,
    Iterable,
    Literal,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
import msgspec
from typing_extensions import TypeAliasType, get_original_bases

if TYPE_CHECKING:
    from .reproca import Method


class HashFile:
    def __init__(
        self, file: IO[str], hasher: Callable[[], hashlib._Hash] = sha512
    ) -> None:
        self.file = file
        self.hash = hasher()

    def write(self, s: str) -> int:
        value = self.file.write(s)
        self.hash.update(s.encode())
        return value

    def writelines(self, strings: Iterable[str]) -> None:
        for string in strings:
            self.write(string)


def get_type_alias_value(obj: TypeAliasType) -> object:
    globalns = getattr(sys.modules.get(obj.__module__, None), "__dict__", {})  # type: ignore
    localns = dict(vars(obj))
    return typing._eval_type(obj.__value__, globalns, localns)  # type: ignore


class Writer:
    def __init__(self, file: IO[str]) -> None:
        self.file = HashFile(file)

    def write(self, *strings: str) -> None:
        self.file.writelines(strings)

    def intersperse(
        self, separator: Callable[[], None], funcs: Iterable[Callable[[], None]]
    ) -> None:
        it = iter(funcs)
        func = next(it, None)
        while func is not None:
            func()
            func = next(it, None)
            if func is not None:
                separator()


class TypeScriptWriter(Writer):
    def __init__(self, file: IO[str]) -> None:
        super().__init__(file)
        self.unresolved: set[type[msgspec.Struct] | TypeAliasType] = set()
        self.resolved: set[object] = set()

    def resolve(self) -> None:
        if len(self.unresolved) == 0:
            return
        self.resolved.update(self.unresolved)
        unresolved = self.unresolved
        self.unresolved = set()
        for obj in unresolved:
            if isinstance(obj, TypeAliasType):
                self.typealias(obj)
            else:
                self.struct(obj)
        self.resolve()

    def typealias(self, obj: TypeAliasType) -> None:
        self.write("export type ", obj.__name__)
        if obj.__type_params__:
            self.write("<")
            self.intersperse(
                lambda: self.write(","),
                (functools.partial(self.type, param) for param in obj.__type_params__),
            )
            self.write(">")
        self.write("=")
        self.type(get_type_alias_value(obj))

    def literal(self, obj: object) -> None:
        match obj:
            case None:
                self.write("null")
            case True:
                self.write("true")
            case False:
                self.write("false")
            case int() | float() | str():
                self.write(repr(obj))
            case _:
                msg = f"Unsupported literal type: {obj!r}"
                raise TypeError(msg)

    def type(self, obj: object) -> None:
        match obj:
            case msgspec.UnsetType():
                self.write("undefined")
            case type() if issubclass(obj, NoneType):
                self.write("null")
            case None:
                self.write("null")
            case type() if issubclass(obj, bool):
                self.write("boolean")
            case type() if issubclass(obj, int | float):
                self.write("number")
            case type() if issubclass(obj, str | bytes | bytearray | datetime):
                self.write("string")
            case type() if issubclass(obj, msgspec.Struct):
                if obj not in self.resolved:
                    self.unresolved.add(obj)
                self.write(obj.__name__)
            case type() if obj is msgspec.UnsetType:
                self.write("undefined")
            case TypeVar():
                self.write(obj.__name__)
            case TypeAliasType():
                if obj not in self.resolved:
                    self.unresolved.add(obj)
                self.write(obj.__name__)
            case _:
                orig = get_origin(obj)
                match orig:
                    case TypeAliasType():
                        args = get_args(obj)
                        if orig not in self.resolved:
                            self.unresolved.add(orig)
                        self.write(orig.__name__)
                        self.write("<")
                        self.intersperse(
                            lambda: self.write(","),
                            (functools.partial(self.type, arg) for arg in args),
                        )
                        self.write(">")
                    case type() if issubclass(orig, msgspec.Struct):
                        args = get_args(obj)
                        if orig not in self.resolved:
                            self.unresolved.add(orig)
                        self.write(orig.__name__)
                        self.write("<")
                        self.intersperse(
                            lambda: self.write(","),
                            (functools.partial(self.type, arg) for arg in args),
                        )
                        self.write(">")
                    case type() if issubclass(orig, tuple):
                        args = get_args(obj)
                        if args[1:] == (...,):
                            self.type(list[args[0]])  # type: ignore
                            return
                        self.write("[")
                        self.intersperse(
                            lambda: self.write(","),
                            (functools.partial(self.type, arg) for arg in args),
                        )
                        self.write("]")
                    case type() if issubclass(
                        orig,
                        list
                        | set
                        | frozenset
                        | Collection
                        | Sequence
                        | MutableSequence
                        | MutableSet,
                    ):
                        self.write("(")
                        self.type(get_args(obj)[0])
                        self.write(")[]")
                    case type() if issubclass(orig, dict | Mapping | MutableMapping):
                        args = get_args(obj)
                        self.write("{[index:")
                        self.type(args[0])
                        self.write("]:")
                        self.type(args[1])
                        self.write("}")
                    case orig if orig is Literal:
                        self.intersperse(
                            lambda: self.write("|"),
                            (
                                functools.partial(self.literal, arg)
                                for arg in get_args(obj)
                            ),
                        )
                    case type() if orig is UnionType:

                        def do(arg: object) -> None:
                            self.write("(")
                            self.type(arg)
                            self.write(")")

                        self.write("(")
                        self.intersperse(
                            lambda: self.write("|"),
                            (functools.partial(do, arg) for arg in get_args(obj)),
                        )
                        self.write(")")
                    case _:
                        msg = f"Unsupported type: {obj!r} type={type(obj)!r}"
                        raise TypeError(msg)

    def struct(self, struct: type[msgspec.Struct]) -> None:
        self.write(f"\n/** {struct.__doc__} */\nexport interface ", struct.__name__)
        if params := next(
            (
                get_args(base)
                for base in get_original_bases(struct)
                if get_origin(base) is Generic
            ),
            None,
        ):
            self.write("<")
            self.intersperse(
                lambda: self.write(","),
                (functools.partial(self.type, param) for param in params),
            )
            self.write(">")
        self.write("{")
        for fieldname, fieldtype in get_type_hints(struct).items():
            optional = False
            if (
                get_origin(fieldtype) is UnionType
                and msgspec.UnsetType in (args := get_args(fieldtype))
                and any(
                    field.default is msgspec.UNSET
                    for field in msgspec.structs.fields(struct)
                )
            ):
                args = (arg for arg in args if arg is not msgspec.UnsetType)
                fieldtype = Union[*args]  # type: ignore
                optional = True
            self.write(fieldname, "?:" if optional else ":")
            self.type(fieldtype)
            self.write(";")
        self.write("}")

    def reproca_method(self, method: Method) -> None:
        self.write(
            f"\n/** {method.func.__doc__} */\nexport async function ",
            method.func.__name__,
            "(",
        )

        def do(name: str, obj: object) -> None:
            self.write(name, ":")
            self.type(obj)

        self.intersperse(
            lambda: self.write(","),
            (functools.partial(do, name, obj) for name, obj in method.params),
        )
        self.write("):Promise<ReprocaMethodResponse<")
        self.type(method.returns)
        self.write(">>{return await reproca.callMethod(", repr(method.path), ",{")
        self.intersperse(
            lambda: self.write(","),
            (functools.partial(self.write, name) for name, _ in method.params),
        )
        self.write("})}")
