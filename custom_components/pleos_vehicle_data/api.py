"""Async client for the official personal API. Tokens stay in memory."""

import asyncio
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import aiohttp

API = "https://api.pleos.ai"
TOKEN_ERRORS = {"401", "4011", "40003", "40004"}


def reject_nonfinite(value):
    raise ValueError("Nonfinite value in JSON response")


class ApiError(Exception):
    def __init__(self, status, code):
        super().__init__(f"Pleos HTTP {status}, code {code}")
        self.status, self.code = status, code


class AuthError(Exception):
    """The personal key needs replacement."""


class PleosClient:
    def __init__(self, session, brand, client_id, client_secret):
        self.session, self.brand = session, brand
        self.credentials = {"clientId": client_id, "clientSecret": client_secret}
        self.token = None
        self.retry_at = 0
        self.response_meta = {}

    async def _request(self, path, body=None):
        if time.monotonic() < self.retry_at:
            raise ApiError(429, "rate_limited")
        headers = {"Brand": self.brand}
        if body is None:
            headers["Authorization"] = "Bearer " + self.token
        try:
            async with self.session.request(
                "GET" if body is None else "POST", API + path, headers=headers,
                json=body, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=False,
            ) as response:
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > 16 * 1024 * 1024:
                        raise ApiError(response.status, "oversized_response")
                if response.status == 429:
                    retry = response.headers.get("Retry-After", "300")
                    try:
                        seconds = int(retry)
                    except ValueError:
                        try:
                            seconds = (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()
                        except (TypeError, ValueError):
                            seconds = 300
                    self.retry_at = time.monotonic() + max(300, seconds)
                try:
                    payload = json.loads(raw, parse_constant=reject_nonfinite)
                except (ValueError, UnicodeDecodeError):
                    raise ApiError(response.status, "invalid_response") from None
                if not isinstance(payload, dict):
                    raise ApiError(response.status, "invalid_response")
                meta = payload.get("meta") or {}
                if not isinstance(meta, dict):
                    raise ApiError(response.status, "invalid_response")
                error = payload.get("error") or meta
                if response.status >= 300 or payload.get("error") or meta.get("success") in (False, "false"):
                    code = str(error.get("code", "unknown")) if isinstance(error, dict) else "unknown"
                    raise ApiError(response.status, code if code.isdigit() else "unknown")
                self.response_meta[path.split("?")[0]] = {
                    key: meta[key] for key in ("code", "message", "success", "timestamp", "requestId") if key in meta
                }
                return payload.get("data")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            # Do not include request URLs (VINs), headers or bodies in exceptions.
            raise ApiError(0, "connection_failed") from None

    async def get(self, path):
        for attempt in range(2):
            if not self.token:
                try:
                    data = await self._request("/v1/auth/personal-token", self.credentials)
                except ApiError as error:
                    if error.status in (401, 403) or error.code in TOKEN_ERRORS | {"40404", "40001"}:
                        raise AuthError("Personal API key expired, revoked or invalid") from None
                    raise
                if not isinstance(data, dict) or not isinstance(data.get("accessToken"), str) or not data["accessToken"]:
                    raise ApiError(200, "missing_token")
                self.token = data["accessToken"]
            try:
                return await self._request(path)
            except ApiError as error:
                # The live API also returns 403 for expired bearer tokens.
                if attempt == 0 and (error.status == 403 or error.code == "403"):
                    self.token = None
                    continue
                if error.status == 401 or error.code in TOKEN_ERRORS:
                    self.token = None
                    if attempt == 0:
                        continue
                    raise AuthError("Personal API key is no longer accepted") from None
                raise

    async def vehicles(self):
        data = await self.get("/v1/vehicles/consent")
        vehicles = data.get("vehicles") if isinstance(data, dict) else None
        if not isinstance(vehicles, list) or any(
            not isinstance(v, dict) or not isinstance(v.get("vin"), str) or not v["vin"] for v in vehicles
        ):
            raise ApiError(200, "invalid_vehicle_list")
        return vehicles
