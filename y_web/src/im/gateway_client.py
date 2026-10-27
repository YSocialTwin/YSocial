"""Client of the IM human gateway (plan 4.8): loopback HTTP with a per-run token.

YWeb never writes the IM database: every participant action and every read for a participant goes through
the gateway, which calls the IM server's own handlers. The address is read from ``human_gateway.json``
(written by the gateway) and the token from ``human_gateway.token`` (written by YWeb when it starts it).
"""

import json
import os
from typing import Any, Dict, Optional, Tuple

import requests

STATE_FILE = "human_gateway.json"
TOKEN_FILE = "human_gateway.token"
TOKEN_HEADER = "X-IM-Gateway-Token"
TIMEOUT = 8


class GatewayUnavailable(RuntimeError):
    """The gateway is not running or does not answer (the page shows 'connection lost')."""


def read_gateway_state(exp_folder: str) -> Optional[dict]:
    try:
        with open(os.path.join(exp_folder, STATE_FILE), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and data.get("port") else None
    except (OSError, ValueError):
        return None


def read_gateway_token(exp_folder: str) -> Optional[str]:
    try:
        with open(os.path.join(exp_folder, TOKEN_FILE), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


class GatewayClient:
    def __init__(self, exp_folder: str, session=None):
        self.exp_folder = exp_folder
        self.session = session or requests

    def _base(self) -> Tuple[str, str]:
        state, token = read_gateway_state(self.exp_folder), read_gateway_token(self.exp_folder)
        if not state or not token:
            raise GatewayUnavailable("gateway is not running")
        return f"http://{state.get('host', '127.0.0.1')}:{int(state['port'])}", token

    def request(self, method: str, path: str, body: Optional[dict] = None, params=None):
        base, token = self._base()
        try:
            resp = self.session.request(
                method,
                base + path,
                json=body,
                params=params,
                headers={TOKEN_HEADER: token},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GatewayUnavailable(str(exc)) from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {"ok": False, "code": "bad_response"}
        return resp.status_code, payload

    # -- operations -------------------------------------------------------------------------
    def state(self):
        return self.request("GET", "/v1/state")

    def ensure(self, key: str, username: str, language: Optional[str] = None):
        return self.request(
            "POST",
            "/v1/humans/ensure",
            {"human_key": key, "username": username, "language": language},
        )

    def actions(self, account_id: str, actions: list):
        return self.request("POST", "/v1/actions", {"account_id": account_id, "actions": actions})

    def chats(self, account_id: str):
        return self.request("GET", "/v1/chats", params={"account_id": account_id})

    def messages(self, account_id: str, chat_id: str, before=None, limit: int = 20):
        params: Dict[str, Any] = {"account_id": account_id, "limit": limit}
        if before:
            params["before"] = before
        return self.request("GET", f"/v1/chats/{chat_id}/messages", params=params)

    def search(self, account_id: str, q: str, chat_id=None, limit: int = 20):
        params: Dict[str, Any] = {"account_id": account_id, "q": q, "limit": limit}
        if chat_id:
            params["chat_id"] = chat_id
        return self.request("GET", "/v1/search", params=params)

    def notifications(self, account_id: str):
        return self.request("GET", "/v1/notifications", params={"account_id": account_id})

    def invite(self, account_id: str, chat_id: str, usage_limit=None):
        return self.request(
            "POST",
            "/v1/invites",
            {"account_id": account_id, "chat_id": chat_id, "usage_limit": usage_limit},
        )
