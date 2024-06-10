from collections.abc import Sequence
from http import HTTPStatus

import msgspec.json

from .asgi.types import (
    ASGIReceiveCallable,
    ASGISendCallable,
    HTTPDisconnectEvent,
    HTTPRequestEvent,
    HTTPScope,
    LifespanShutdownEvent,
    LifespanStartupEvent,
    Scope,
    WebSocketConnectEvent,
    WebSocketDisconnectEvent,
    WebSocketReceiveEvent,
)
from .credentials import Credentials
from .memcache import Memcache
from .method import methods
from .sessions import Sessions

encoder = msgspec.json.Encoder()


def get_headers(scope: HTTPScope) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in scope["headers"]}


async def send_response_header(
    status: HTTPStatus,
    send: ASGISendCallable,
    headers: Sequence[tuple[bytes, bytes]],
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )


async def send_response(body: bytes, send: ASGISendCallable) -> None:
    await send({"type": "http.response.body", "body": body})


class App[T, U]:
    def __init__(
        self,
        sessions: Sessions[T, U],
        memcache: Memcache,
    ) -> None:
        self.memcache = memcache
        self.sessions = sessions

    async def __call__(
        self,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        request = await receive()
        match request["type"]:
            case "http.request":
                assert scope["type"] == "http"
                await self.on_request(scope, request, send)
            case "http.disconnect":
                await self.on_disconnect(scope, request, send)
            case "lifespan.startup":
                await self.on_startup(scope, request, send)
            case "lifespan.shutdown":
                await self.on_shutdown(scope, request, send)
            case "websocket.connect":
                await self.on_websocket_connect(scope, request, send)
            case "websocket.receive":
                await self.on_websocket_receive(scope, request, send)
            case "websocket.disconnect":
                await self.on_websocket_disconnect(scope, request, send)

    async def on_request(
        self,
        scope: HTTPScope,
        event: HTTPRequestEvent,
        send: ASGISendCallable,
    ) -> None:
        headers = get_headers(scope)
        response_headers: list[tuple[bytes, bytes]] = [
            # Bypass CORS, could be dangerous?
            (b"Access-Control-Allow-Credentials", b"true"),
            (b"Content-Type", b"application/json"),
        ]
        if b"origin" in headers:
            response_headers.append(
                (b"Access-Control-Allow-Origin", headers[b"origin"])
            )
        assert scope["client"] is not None
        address = scope["client"][0]
        try:
            method = methods[scope["path"]]
        except KeyError:
            await send_response_header(
                HTTPStatus.BAD_REQUEST, send, headers=response_headers
            )
            await send_response(b"Method does not exist", send)
            return
        if method.rate_limit > 0 and self.memcache.rate_limit(
            address, scope["path"], method.rate_limit
        ):
            await send_response_header(
                HTTPStatus.TOO_MANY_REQUESTS, send, headers=response_headers
            )
            await send_response(b"Rate limit exceeded", send)
            return
        try:
            parameters = method.decoder.decode(event["body"])
        except (msgspec.DecodeError, msgspec.ValidationError):
            await send_response_header(
                HTTPStatus.BAD_REQUEST, send, headers=response_headers
            )
            await send_response(b"Invalid parameters", send)
            return
        args = msgspec.structs.asdict(parameters)
        credentials = Credentials(headers.get(b"cookie", None))
        if "credentials" in method.type_hints:
            args["credentials"] = credentials
        if "session" in method.type_hints:
            args["session"] = None
            if sessionid := credentials.get_session():
                args["session"] = self.sessions.get_by_sessionid(sessionid)
            if not method.parameter_session_optional and args["session"] is None:
                await send_response_header(
                    HTTPStatus.UNAUTHORIZED, send, headers=response_headers
                )
                await send_response(b"Invalid session", send)
                return
        body = encoder.encode(await method.implementation(**args))
        if "credentials" in method.type_hints:
            response_headers.extend(credentials._headers)
        await send_response_header(HTTPStatus.OK, send, headers=response_headers)
        await send_response(body, send)

    async def on_disconnect(
        self,
        scope: Scope,
        event: HTTPDisconnectEvent,
        send: ASGISendCallable,
    ) -> None:
        pass

    async def on_startup(
        self,
        scope: Scope,
        event: LifespanStartupEvent,
        send: ASGISendCallable,
    ) -> None:
        pass

    async def on_shutdown(
        self,
        scope: Scope,
        event: LifespanShutdownEvent,
        send: ASGISendCallable,
    ) -> None:
        pass

    async def on_websocket_connect(
        self,
        scope: Scope,
        event: WebSocketConnectEvent,
        send: ASGISendCallable,
    ) -> None:
        pass

    async def on_websocket_receive(
        self,
        scope: Scope,
        event: WebSocketReceiveEvent,
        send: ASGISendCallable,
    ) -> None:
        pass

    async def on_websocket_disconnect(
        self,
        scope: Scope,
        event: WebSocketDisconnectEvent,
        send: ASGISendCallable,
    ) -> None:
        pass
