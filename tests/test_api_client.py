"""Personal-token handling and HTTP response validation in the API client."""

import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.pleos_vehicle_data.api import ApiError, AuthError

from support import HomeAssistantTestCase


class ApiClientTests(HomeAssistantTestCase):
    async def test_short_lived_token_refreshes_once(self):
        self.client._request = AsyncMock(side_effect=[{"accessToken": "old"}, ApiError(400, "40003"), {"accessToken": "new"}, {"vehicles": []}])
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client._request.await_count, 4)
        self.assertEqual(self.client.token, "new")

    async def test_expired_token_403_refreshes_and_reuses_new_token(self):
        self.client.token = "expired-fixture-token"
        def response(status, payload):
            result = MagicMock()
            result.status = status
            async def chunks(size):
                yield json.dumps(payload).encode()
            result.content.iter_chunked = chunks
            context = MagicMock()
            context.__aenter__.return_value = result
            return context
        self.client.session.request.side_effect = [
            response(403, {"error": {"code": 403}}),
            response(200, {"data": {"accessToken": "renewed-fixture-token"}}),
            response(200, {"data": {"vehicles": []}}),
            response(200, {"data": {"vehicles": []}}),
        ]
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client.token, "renewed-fixture-token")
        requests = self.client.session.request.call_args_list
        self.assertEqual([call.args[0] for call in requests], ["GET", "POST", "GET", "GET"])
        self.assertEqual(requests[0].kwargs["headers"]["Authorization"], "Bearer expired-fixture-token")
        self.assertEqual(requests[2].kwargs["headers"]["Authorization"], "Bearer renewed-fixture-token")

    async def test_persistent_403_is_permission_error_and_keeps_fresh_token(self):
        self.client.token = "old"
        self.client._request = AsyncMock(side_effect=[ApiError(403, "403"), {"accessToken": "fresh"}, ApiError(403, "403"), {"vehicles": []}])
        with self.assertRaises(ApiError) as caught:
            await self.client.get("/v1/vehicles/SYNTHETIC-CAR-001/locations")
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(self.client._request.await_count, 3)
        self.assertEqual(self.client.token, "fresh")
        self.assertEqual(await self.client.vehicles(), [])
        self.assertEqual(self.client._request.await_count, 4)

    async def test_expired_key_after_403_requires_reauth(self):
        self.client.token = "expired"
        self.client._request = AsyncMock(side_effect=[ApiError(403, "403"), ApiError(404, "40404")])
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 2)

    async def test_invalid_key_requires_reauth(self):
        self.client._request = AsyncMock(side_effect=ApiError(404, "40404"))
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 1)

    async def test_repeated_token_rejection_stops_retry(self):
        self.client._request = AsyncMock(side_effect=[{"accessToken": "one"}, ApiError(400, "4011"), {"accessToken": "two"}, ApiError(400, "4011")])
        with self.assertRaises(AuthError):
            await self.client.vehicles()
        self.assertEqual(self.client._request.await_count, 4)

    async def test_nonfinite_json_is_rejected(self):
        response = MagicMock()
        response.status = 200
        async def chunks(size):
            yield b'{"data": {"temperature": NaN}}'
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertEqual(caught.exception.code, "invalid_response")

    async def test_rate_limit_does_not_make_network_requests(self):
        self.client.retry_at = time.monotonic() + 300
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/vehicles/consent")
        self.assertEqual(caught.exception.status, 429)
        self.client.session.request.assert_not_called()

    async def test_http_errors_and_rate_limit_header(self):
        response = MagicMock()
        response.status = 429
        response.headers = {"Retry-After": "1200"}
        async def chunks(size):
            yield json.dumps({"meta": {"success": False, "code": "429"}}).encode()
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError) as caught:
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertEqual(caught.exception.status, 429)
        self.assertGreater(self.client.retry_at, time.monotonic() + 1190)

    async def test_http_schema_and_redirect_boundary(self):
        response = MagicMock()
        response.status = 200
        response.headers = {}
        async def chunks(size):
            yield b'{"meta": "invalid", "data": null}'
        response.content.iter_chunked = chunks
        self.client.session.request.return_value.__aenter__.return_value = response
        with self.assertRaises(ApiError):
            await self.client._request("/v1/auth/personal-token", self.client.credentials)
        self.assertFalse(self.client.session.request.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
