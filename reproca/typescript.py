from __future__ import annotations
import functools
import sys
import typing
from datetime import datetime
from types import UnionType
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


def get_type_alias_value(obj: TypeAliasType) -> object:
    globalns = getattr(sys.modules.get(obj.__module__, None), "__dict__", {})  # type: ignore
    localns = dict(vars(obj))
    return typing._eval_type(obj.__value__, globalns, localns)  # type: ignore


class Writer:
    def __init__(self, file: IO[str]) -> None:
        self.file = file

    def write(self, *strings: str) -> None:
        for string in strings:
            self.file.write(string)

    def intersperse(
        self, separator: Callable[[], None], callbacks: Iterable[Callable[[], None]]
    ) -> None:
        sentinel = object()
        it = iter(callbacks)
        nxt = next(it, sentinel)
        while nxt is not sentinel:
            nxt()  # type: ignore
            nxt = next(it, sentinel)
            if nxt is not sentinel:
                separator()


class TypeScriptWriter(Writer):
    def __init__(self, file: IO[str]) -> None:
        super().__init__(file)
        self.unresolved: set[type[msgspec.Struct] | TypeAliasType] = set()
        self.resolved = set[object]()

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
                        if len(args) == 2 and args[1] is ...:
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
                        (
                            list,
                            set,
                            frozenset,
                            Collection,
                            Sequence,
                            MutableSequence,
                            MutableSet,
                        ),
                    ):
                        args = get_args(obj)
                        self.write("(")
                        self.type(args[0])
                        self.write(")[]")
                    case type() if issubclass(orig, (dict, Mapping, MutableMapping)):
                        args = get_args(obj)
                        self.write("{[index:")
                        self.type(args[0])
                        self.write("]:")
                        self.type(args[1])
                        self.write("}")
                    case type() if orig is Literal:
                        args = get_args(obj)
                        self.intersperse(
                            lambda: self.write("|"),
                            (functools.partial(self.literal, arg) for arg in args),
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

    def struct(self, obj: type[msgspec.Struct]) -> None:
        ann = get_type_hints(obj)
        params = next(
            (
                get_args(base)
                for base in get_original_bases(obj)
                if get_origin(base) is Generic
            ),
            None,
        )
        self.write("export interface ", obj.__name__)
        if params:
            self.write("<")
            self.intersperse(
                lambda: self.write(","),
                (functools.partial(self.type, param) for param in params),
            )
            self.write(">")
        self.write("{")
        for name, obj2 in ann.items():
            optional = False
            if (
                get_origin(obj2) is UnionType
                and (msgspec.UnsetType in (args := get_args(obj2)))
                and any(
                    True
                    for field in msgspec.structs.fields(obj)
                    if field.default is msgspec.UNSET
                )
            ):
                args = (arg for arg in args if arg is not msgspec.UnsetType)
                obj2 = Union[*args]  # type: ignore
                optional = True
            self.write(name, "?:" if optional else ":")
            self.type(obj2)
            self.write(";")
        self.write("}")

    def reproca_method(self, method: Method) -> None:
        self.write("export async function ", method.func.__name__, "(")

        def do(name: str, obj: object) -> None:
            self.write(name, ":")
            self.type(obj)

        self.intersperse(
            lambda: self.write(","),
            (functools.partial(do, name, obj) for name, obj in method.params),
        )
        self.write("):Promise<ReprocaMethodResponse<")
        self.type(method.returns)
        self.write(">>{return await reproca.call_method(", repr(method.path), ",{")

        for i, (name, _) in enumerate(method.params):
            self.write(name)
            if i < len(method.params) - 1:
                self.write(",")
        self.write("})}")
