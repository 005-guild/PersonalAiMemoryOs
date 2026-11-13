"""Bounded HTTP transport; protocol adapters never perform network I/O."""

import asyncio
import json

import httpx

from app.agents.configuration import ResolvedProfile
from app.agents.errors import AIError
from app.agents.protocols import ModelReply, build_request, parse_response

MAX_RESPONSE_BYTES = 1024 * 1024


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite response value.")


class ModelClient:
    """No implicit retry, redirect, streaming output, or protocol fallback."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def aclose(self) -> None:
        """Each generate call owns and closes its HTTP client and response stream."""

    async def generate(self, resolved: ResolvedProfile, system_prompt: str, user_prompt: str, *, images=None) -> ModelReply:
        url, headers, body = build_request(resolved, system_prompt, user_prompt)
        if images:
            if resolved.profile.protocol != 'openai_chat' or len(images)>4:
                raise AIError(422, 'unsupported_image_request')
            if any(not isinstance(value,str) or not value.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/gif;base64,','data:image/webp;base64,')) for value in images):
                raise AIError(422, 'invalid_image_request')
            body['messages'][-1]['content']=[{'type':'text','text':user_prompt}, *[
                {'type':'image_url','image_url':{'url':value,'detail':'original'}} for value in images]]
            if len(json.dumps(body).encode())>32*1024*1024:
                raise AIError(422, 'image_request_too_large')
        timeout = resolved.profile.timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    transport=self.transport, follow_redirects=False,
                    timeout=httpx.Timeout(timeout),
                ) as client:
                    async with client.stream("POST", url, headers=headers, json=body) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            raise AIError(502, "ai_upstream_error")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise AIError(502, "ai_response_too_large")
                            raw.extend(chunk)
                        try:
                            payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_keys,
                                                 parse_constant=_invalid_constant)
                        except (UnicodeError, ValueError, RecursionError):
                            raise AIError(502, "invalid_model_response") from None
                        return parse_response(resolved.profile.protocol, payload)
        except (TimeoutError, httpx.TimeoutException):
            raise AIError(504, "ai_timeout") from None
        except httpx.HTTPError:
            raise AIError(502, "ai_upstream_error") from None
