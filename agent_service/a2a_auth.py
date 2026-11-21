"""Authenticate A2A callers independently of any ingress identity."""

import json
import os
import re
import secrets

from a2a.auth.user import User
from a2a.server.context import ServerCallContext
from a2a.server.routes.jsonrpc_dispatcher import DefaultServerCallContextBuilder
from starlette.exceptions import HTTPException
from starlette.requests import Request

_NAME = re.compile(r"[A-Za-z0-9._@-]{1,128}\Z")
_KEY = re.compile(r"[A-Za-z0-9_-]{43,256}\Z")


class _Caller(User):
    def __init__(self, name: str):
        self._name = name

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return self._name


class CallerContextBuilder(DefaultServerCallContextBuilder):
    def __init__(self):
        raw = os.environ.get("QE_A2A_CLIENT_KEYS", "")
        try:
            keys = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise ValueError("QE_A2A_CLIENT_KEYS must be a JSON object") from exc
        if (not isinstance(keys, dict)
                or any(not isinstance(name, str) or not _NAME.fullmatch(name)
                       or not isinstance(key, str) or not _KEY.fullmatch(key)
                       for name, key in keys.items())
                or len(set(keys.values())) != len(keys)):
            raise ValueError("QE_A2A_CLIENT_KEYS must contain unique client names and keys")
        self._keys = keys

    def build(self, request: Request) -> ServerCallContext:
        context = super().build(request)
        context.state["headers"].pop("x-qe-a2a-key", None)
        return context

    def build_user(self, request: Request) -> User:
        supplied = request.headers.get("X-QE-A2A-Key", "")
        if _KEY.fullmatch(supplied):
            for name, key in self._keys.items():
                if secrets.compare_digest(supplied, key):
                    return _Caller(name)
        raise HTTPException(status_code=401, detail="A2A client authentication required")
