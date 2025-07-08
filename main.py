from __future__ import annotations

from reproca import create_starlette_application, method


@method
async def add(left: int, right: int) -> int:
    """Add two numbers."""
    return left + right


app = create_starlette_application()
