```py
from __future__ import annotations

import msgspec

import reproca.sessions
from reproca import create_starlette_application, method


class User(msgspec.Struct):
    # put any additional fields you would like to store in sessions, they can be
    # accessed inside any method using the `session` parameter, if the user is
    # authenticated.
    additional_data: str


sessions = Sessions[User]()

@method
async def function_name(param_name: int) -> int:
    return param_name * 1000

app = create_starlette_application(sessions)
```

use `base="/api/"` to set the base path for all methods (only applies to methods).

### Methods

The function name is the endpoint `function_name` -> `curl -X POST https://example.com/function-name/`

Parameters can be passed as query params, x-headers or JSON body.

Object keys, parameter names, method names are Case-insensitive, dash (`-`) is converted into (`_`) automatically.

Always use type annotations for methods, they are used for validation.

For JSON objects, use `msgspec.Struct`, see msgspec documentation for more information.

Return either starlette `Response` objects, or return JSON serializable objects such as
dictionaries, lists or msgpsec structs (preferable).

If you need access to cookies, headers, etc. Take in a `request: starlette.requests.Request`
parameter.

### Sessions

If a method takes in a `session` parameter. It will check if the user is authenticated
before calling the method. If `session`'s type annotation is an optional (i.e `T|None`)
then it will allow accessing the endpoint even if the user isn't authenticated, in which
case `session` will be passed as `None`. Otherwise, the request will be rejected
with unauthorized status.

```py
@method
async def i_need_auth(session: tuple[str, User]) -> None:
    pass

@method
async def i_dont_need_auth(session: tuple[str, User] | None) -> None:
    pass
```

The type annotation of the `session` parameter must be `tuple[str, User]` or
`tuple[str, User] | None`

`session[0]` is the user's ID. it can be anything such as the username or user ID.

`session[1]` is an object that may store any additional data you might need, such
as the permissions of the user. This is stored on the backend, not transferred to the 
frontend.

### Authentication

It's your responsibility to implement login and logout methods.

```py
@method
async def login(username: str, password: str) -> None:
    if username == "admin" and password == "admin":
        return sessions.create_session_cookie(username, User(additional_data="hello"), Response())
```

logout can be implemented like this:

```py
@method
async def logout(session: tuple[str, object] | None) -> None:
    if session is not None:
        sessions.remove(session[0])
```
