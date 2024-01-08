# name   : byte byte byte byte
# u64    : little-endian 64-bit unsigned integer
# i64    : little-endian 64-bit signed integer
# f64    : IEEE 754 binary64
# str    : unicode string
# NONE   : 0x01
# TRUE   : 0x02
# FALSE  : 0x03
# INT    : 0x04 value=i64
# FLOAT  : 0x05 value=f64
# STRING : 0x06 value=str 0x00
# BYTES  : 0x07 length=u64 values=byte*
# LIST   : 0x08 size=u64 values=VALUE*
# OBJECT : 0x09 size=u64 items=(key=name value=VALUE)*
# VALUE  : NONE
#        | TRUE
#        | FALSE
#        | INT
#        | FLOAT
#        | STRING
#        | BYTES
#        | LIST
#        | OBJECT

from __future__ import annotations

import itertools
import struct
from collections.abc import Mapping
from io import BytesIO
from typing import IO, cast

Value = None | bool | int | float | str | bytes | list['Value'] | dict[str, 'Value']


def value(stream: IO[bytes]) -> tuple[Value, int]:
    def u64():
        return cast(int, struct.unpack("<Q", stream.read(8))[0])

    type = stream.read(1)[0]
    if type == 0x01:
        return None, 1
    if type == 0x02:
        return True, 1
    if type == 0x03:
        return False, 1
    if type == 0x04:
        return cast(int, *struct.unpack("<q", stream.read(8))), 9
    if type == 0x05:
        return cast(float, *struct.unpack("<d", stream.read(8))), 9
    if type == 0x06:
        data = bytearray()
        while (byte := stream.read(1)) != b"\x00":
            data.append(*byte)
        return data.decode("utf-8"), len(data) + 2
    if type == 0x07:
        size = u64()
        return stream.read(size), size + 9
    if type == 0x08:
        data = []
        size = u64()
        i = size
        while i > 0:
            item, itemsize = value(stream)
            i -= itemsize
            data.append(item)
        return data, size + 9
    if type == 0x09:
        data = {}
        size = u64()
        i = size
        while i > 0:
            key = stream.read(4).decode("ascii").rstrip("\x00")
            i -= 4
            item, itemsize = value(stream)
            i -= itemsize
            data[key] = item
        return data, size + 9
    raise TypeError


def seek(stream: IO[bytes], selector: list[str | int]) -> Value:
    def skip():
        type = stream.read(1)[0]
        if type in (0x04, 0x05):
            stream.seek(8)

    if isinstance(selector[0], str):
        stream.read(1)
        if selector[0] == stream.read(3).decode("ascii").rstrip("\x00"):
            skip()

    else:
        raise NotImplementedError


def serialize(value: object, buffer: bytearray):
    if value is None:
        buffer.append(0x01)
        return
    if value is True:
        buffer.append(0x02)
        return
    if value is False:
        buffer.append(0x03)
        return
    if isinstance(value, int):
        buffer.append(0x04)
        buffer.extend(struct.pack("<q", value))
        return
    if isinstance(value, float):
        buffer.append(0x05)
        buffer.extend(struct.pack("<d", value))
        return
    if isinstance(value, str):
        buffer.append(0x06)
        buffer.extend(value.encode("utf-8"))
        buffer.append(0x00)
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        buffer.append(0x07)
        buffer.extend(struct.pack("<Q", len(value)))
        buffer.extend(value)
        return
    if isinstance(value, Mapping):
        buffer.append(0x09)
        for _ in range(8):
            buffer.append(0)
        length = len(buffer)
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError
            key = key.encode("ascii")[:4]
            buffer.extend(key)
            for _ in range(4 - len(key)):
                buffer.append(0)
            serialize(item, buffer)
        size = struct.pack("<Q", len(buffer) - length)
        buffer[length - 8 : length] = size
        return
    try:
        it = iter(value)  # type: ignore
        buffer.append(0x08)
        for _ in range(8):
            buffer.append(0)
        length = len(buffer)
        for value in it:
            serialize(value, buffer)
        size = struct.pack("<Q", len(buffer) - length)
        buffer[length - 8 : length] = size
        return
    except TypeError:
        pass


def unpack(data: IO[bytes] | bytes | bytearray | memoryview) -> Value:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return value(BytesIO(data))[0]
    return value(data)[0]


def pack(value: object) -> bytearray:
    buffer = bytearray()
    serialize(value, buffer)
    return buffer


def hexdump(data: bytes|bytearray):
    for batch in itertools.batched(data, 16):
        print(end="|")
        for i in batch:
            print(hex(i)[2:].rjust(2, "0"), end="|")
        print()


sample = {
    "ID": 0,
    "NAME": "aspizu",
    "ADMN": True,
}
packed = pack(sample)
hexdump(packed)
unpacked = unpack(packed)
print(unpacked)
