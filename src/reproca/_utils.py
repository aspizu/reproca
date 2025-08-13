from __future__ import annotations


def unwrap[T](value: T | None) -> T:
    if value is None:
        msg = "Value cannot be None"
        raise ValueError(msg)
    return value
