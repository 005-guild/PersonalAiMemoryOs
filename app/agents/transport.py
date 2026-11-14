"""Bounded HTTP transport; protocol adapters never perform network I/O."""

import asyncio
import json

import httpx

from app.agents.configuration import ResolvedProfile
from app.agents.errors import AIError
from app.agents.protocols import ModelReply, build_request, parse_response
from app.agents.proxy import model_proxy

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
        url, headers, body = build_request(resolved, system_prompt, user_prompt, images=images)
        return parse_response(resolved.profile.protocol, await self._post(resolved, url, headers, body))

    async def count_input_tokens(self, resolved: ResolvedProfile, system_prompt: str, user_prompt: str, *, images=None) -> int:
        if resolved.profile.protocol != 'openai_responses':
            raise AIError(422, 'token_count_unsupported')
        _, headers, generation = build_request(resolved, system_prompt, user_prompt, images=images)
        body = {key:generation[key] for key in ('model','instructions','input') if key in generation}
        value = await self._post(resolved, resolved.profile.base_url+'/responses/input_tokens', headers, body)
        count = value.get('input_tokens') if isinstance(value,dict) else None
        if (not isinstance(value,dict) or value.get('object')!='response.input_tokens'
                or type(count) is not int or not 0<=count<=2_000_000):
            raise AIError(502, 'invalid_token_count')
        return count

    async def _post(self, resolved, url, headers, body):
        if len(json.dumps(body).encode())>32*1024*1024:
            raise AIError(422, 'image_request_too_large')
        timeout = resolved.profile.timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    transport=self.transport, follow_redirects=False,
                    proxy=model_proxy(url) if self.transport is None else None,
                    timeout=httpx.Timeout(timeout),
                ) as client:
                    async with client.stream("POST", url, headers=headers, json=body) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            error=AIError(502,"ai_upstream_error")
                            error.provider_status=response.status_code
                            raw_error=bytearray()
                            async for piece in response.aiter_bytes():
                                if len(raw_error)+len(piece)>16384:break
                                raw_error.extend(piece)
                            try:
                                failure=json.loads(raw_error).get('error',{})
                                code=failure.get('code')
                                parameter=failure.get('param')
                                if code in {'insufficient_quota','invalid_api_key','model_not_found','rate_limit_exceeded',
                                            'unsupported_value','unsupported_parameter','invalid_request_error','permission_denied'}:
                                    error.provider_code=code
                                if parameter in {'model','reasoning.effort','max_output_tokens','text.format','text.format.type','service_tier','input','store'}:
                                    error.provider_parameter=parameter
                            except (ValueError,AttributeError,TypeError):pass
                            raise error
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
                        return payload
        except (TimeoutError, httpx.TimeoutException):
            raise AIError(504, "ai_timeout") from None
        except httpx.HTTPError:
            raise AIError(502, "ai_upstream_error") from None
