from datetime import datetime
from email.utils import format_datetime
from http import cookies as http_cookies
from typing import Literal


def cookie_parser(cookie_string: str) -> dict[str, str]:
    """Parse a ``Cookie`` HTTP header into a dict of key/value pairs.

    It attempts to mimic browser cookie parsing behavior: browsers and web servers
    frequently disregard the spec (RFC 6265) when setting and reading cookies,
    so we attempt to suit the common scenarios here.

    This function has been adapted from Django 3.1.0.
    Note: we are explicitly _NOT_ using `SimpleCookie.load` because it is based
    on an outdated spec and will fail on lots of input we want to support
    """
    cookie_dict: dict[str, str] = {}
    for chunk in cookie_string.split(";"):
        if "=" in chunk:
            key, val = chunk.split("=", 1)
        else:
            # Assume an empty name per
            # https://bugzilla.mozilla.org/show_bug.cgi?id=169091
            key, val = "", chunk
        key, val = key.strip(), val.strip()
        if key or val:
            # unquote using Python's algorithm.
            cookie_dict[key] = http_cookies._unquote(val)
    return cookie_dict


class Credentials:
    def __init__(self, cookie_string: bytes | None) -> None:
        if cookie_string is not None:
            self.credentials = cookie_parser(cookie_string.decode("latin-1"))
        else:
            self.credentials = {}
        self._headers = []

    def set_session(self, sessionid: str | None) -> None:
        self.set_credential("sessionid", sessionid)

    def get_session(self) -> str | None:
        return self.credentials.get("sessionid")

    def set_credential(self, key: str, value: str | None) -> None:
        if value is None:
            self.credentials.pop(key, None)
        else:
            self.credentials[key] = value
        self.set_cookie(
            key,
            value or "",
            secure=True,
            httponly=True,
            samesite="none",
            partitioned=False,  # Change to True when http.cookies supports it
        )

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: int | None = None,
        expires: datetime | str | int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Literal["lax", "strict", "none"] | None = "lax",
        partitioned: bool = False,
    ) -> None:
        cookie = http_cookies.SimpleCookie()
        cookie[key] = value
        if max_age is not None:
            cookie[key]["max-age"] = max_age
        if expires is not None:
            if isinstance(expires, datetime):
                cookie[key]["expires"] = format_datetime(expires, usegmt=True)
            else:
                cookie[key]["expires"] = expires
        cookie[key]["path"] = path
        if domain is not None:
            cookie[key]["domain"] = domain
        if secure:
            cookie[key]["secure"] = True
        if httponly:
            cookie[key]["httponly"] = True
        if samesite is not None:
            cookie[key]["samesite"] = samesite
        if partitioned:
            cookie[key]["partitioned"] = True
        cookie_val = cookie.output(header="").strip()
        self._headers.append((b"set-cookie", cookie_val.encode("latin-1")))
