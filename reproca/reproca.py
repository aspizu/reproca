from __future__ import annotations
from reproca.typescript import TypeScriptWriter

__all__ = ["Reproca"]

from importlib.resources import files
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Coroutine,
    Generic,
    Mapping,
    ParamSpec,
    Sequence,
    TypeVar,
    Union,
    get_origin,
    get_type_hints,
)
import msgspec
import starlette.responses
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import BaseRoute, Route
from reproca.response import Response
from reproca.sessions import Sessions
from . import resources

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from starlette.middleware import Middleware
    from starlette.types import ExceptionHandler, Lifespan


class Method(msgspec.Struct):
    path: str
    handler: Any
    func: Any
    params: list[tuple[str, object]]
    returns: object


PAR = ParamSpec("PAR")
RET = TypeVar("RET")
ID = TypeVar("ID")
USER = TypeVar("USER")


class Reproca(Generic[ID, USER]):
    def __init__(self) -> None:
        self.sessions: Sessions[ID, USER] = Sessions()
        self.methods: list[Method] = []

    def build(
        self,
        *,
        debug: bool = False,
        routes: Sequence[BaseRoute] | None = None,
        middleware: Sequence[Middleware] | None = None,
        exception_handlers: Mapping[Any, ExceptionHandler] | None = None,
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        lifespan: Lifespan[Starlette] | None = None,
    ) -> Starlette:
        if routes is None:
            routes = []
        
        else:
            routes = list(routes)

        routes.append(Route("/logout", self._logout, methods=["POST"]))

        for method in self.methods:
            routes.append(Route(method.path, method.handler, methods=["POST"]))

        if debug:
            routes.append(Route("/docs", self._docs, methods=["GET"]))
            routes.append(
                Route(
                    "/docs.css",
                    self._resource_file("docs.css", "text/css"),
                    methods=["GET"],
                )
            )

        return Starlette(
            debug=debug,
            middleware=middleware,
            exception_handlers=exception_handlers,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            routes=routes,
        )

    def _resource_file(
        self,
        path: str,
        content_type: str = "text/plain"
    ) -> Callable[[Request], Coroutine[Any, Any, starlette.responses.Response]]:

        async def handler(_request: Request) -> starlette.responses.Response:
            return starlette.responses.Response(
                (files(resources) / path).read_text(),
                headers={"Content-Type": content_type},
            )

        return handler

    async def _docs(self, _request: Request) -> starlette.responses.HTMLResponse:
        return starlette.responses.HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <title>Reproca API Documentation</title>
                    <link rel="stylesheet" href="/docs.css" />
                </head>
                <body>
                    <div class="Methods col p-4 g-4">
                        {"".join(f'''
                        <div class="Method col p-2">
                            <div class="row g-2">
                                <span class="Method__path">{method.path}</span>
                                <span class="Method__name">{method.func.__name__}()</span>
                            </div>
                            {f'<span class="Method__doc">{method.func.__doc__}</span>'
                            if method.func.__doc__ else ''}
                            <div class="Params col">
                            <span class="Params__title">Parameters:</span>
                            <div class="row g-1">
                                {"".join(
                                f'<span class="Params__param">{name}</span>'
                                for name, _ in method.params)}
                            </div>
                            </div>
                        </div>
                        ''' for method in self.methods)}
                    </div>
                </body>
            </html>
            """
        )

    async def _logout(self, request: Request) -> starlette.responses.Response:
        if sessionid := request.cookies.get("reproca_session_id"):
            self.sessions.remove_by_sessionid(sessionid)

        response = starlette.responses.Response()
        response.delete_cookie(
            "reproca_session_id",
            secure=True,
            httponly=True,
            samesite="strict",
        )

        return response

    def method(
        self,
        func: Callable[PAR, Awaitable[RET]]
    ) -> Callable[PAR, Awaitable[RET]]:
        ann = get_type_hints(func)

        if "return" not in ann:
            msg = f"Return type annotation missing for method {func.__name__}."
            raise SyntaxError(msg)

        pass_request = False

        if obj := ann.get("request"):
            if obj is not Request:
                msg = f"Type of request must be {Request} in method {func.__name__}."
                raise SyntaxError(msg)
            pass_request = True

        pass_response = False

        if obj := ann.get("response"):
            if obj is not Response:
                msg = f"Type of response must be {Response} in method {func.__name__}."
                raise SyntaxError(msg)

            pass_response = True

        pass_session = False
        pass_session_optional = False

        if obj := ann.get("session"):
            pass_session = True
            if get_origin(obj) is Union:
                pass_session_optional = True

        params = [
            (argname, argtype)
            for argname, argtype in ann.items()
            if argname not in ["return", "request", "response", "session"]
        ]

        payloadtype = msgspec.defstruct("payloadtype", params)

        async def handler(request: Request) -> starlette.responses.Response:
            try:
                body = msgspec.json.decode(await request.body(), type=payloadtype)

            except msgspec.DecodeError:
                return starlette.responses.Response(status_code=400)

            response_params = Response()
            kwargs = {param: getattr(body, param) for param, _ in params}

            if pass_request:
                kwargs["request"] = request

            if pass_response:
                kwargs["response"] = response_params

            if pass_session:
                session = None
                if sessionid := request.cookies.get("reproca_session_id"):
                    session = self.sessions.get_by_sessionid(sessionid)

                if not pass_session_optional and session is None:
                    return starlette.responses.Response(status_code=401)

                kwargs["session"] = session

            body = await func(**kwargs)  # type: ignore
            response = starlette.responses.Response(
                msgspec.json.encode(body),
                headers={"Content-Type": "application/json", **response_params.headers},
            )

            for cookie in response_params.cookies:
                response.set_cookie(*cookie)

            return response

        self.methods.append(
            Method(f"/{func.__name__}", handler, func, params, ann["return"])
        )

        return func

    def typescript(self, file: IO[str]) -> None:
        writer = TypeScriptWriter(file)
        writer.write(
            'import {ReprocaMethodResponse} from "./reproca.ts";'
            'import reproca from "./reproca_config.ts";'
        )
        for method in self.methods:
            writer.reproca_method(method)

        writer.resolve()
