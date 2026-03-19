"""Provider-agnostic async LLM client for the ToM-PE pipeline.

Supports OpenAI, Anthropic, Ollama (authenticated, streaming), and Together AI —
all through a unified interface. Adapted from the project's existing synchronous
LLM client pattern (code_examples/llm_client.py) but made fully async with httpx.

Usage:
    client = make_client("openai", model="gpt-4.1")
    text = await client.complete_text(system="You are a translator.", user="Translate...")
    data = await client.complete_json(system="...", user="...", schema={...})
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Default concurrency limit across all LLM calls
_DEFAULT_SEMAPHORE_LIMIT = 5
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore(limit: int = _DEFAULT_SEMAPHORE_LIMIT) -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(limit)
    return _semaphore


def _is_reasoning_model(model: str) -> bool:
    """Check if an OpenAI model is a reasoning model (o-series, gpt-5-nano)."""
    m = model.lower()
    if m.startswith(("o1", "o3", "o4")):
        return True
    if "gpt-5-nano" in m:
        return True
    return False


@dataclass
class LLMClient:
    """Async OpenAI-compatible chat completions client with streaming support.

    Works with OpenAI, Ollama (native + /v1), Together AI, and any
    provider exposing the OpenAI /v1/chat/completions endpoint.
    For Anthropic, uses the native Messages API.
    """

    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 4096
    max_retries: int = 3
    timeout: int = 120

    # Internal tracking
    _call_count: int = field(default=0, init=False, repr=False)
    _total_tokens: int = field(default=0, init=False, repr=False)
    _total_latency_ms: float = field(default=0.0, init=False, repr=False)

    async def _raw_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> dict:
        """Low-level chat completion with streaming and retries.

        Returns a dict in OpenAI response format regardless of provider.
        """
        if self.provider == "anthropic":
            return await self._anthropic_chat(
                messages, temperature, max_tokens, response_format
            )

        temp = temperature if temperature is not None else self.temperature
        mtok = max_tokens if max_tokens is not None else self.max_tokens

        # Determine URL and payload format
        use_native_ollama = self.provider == "ollama" and "/v1" not in self.base_url
        if use_native_ollama:
            url = f"{self.base_url.rstrip('/')}/api/chat"
        else:
            url = f"{self.base_url.rstrip('/')}/chat/completions"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        is_reasoning = self.provider == "openai" and _is_reasoning_model(self.model)

        # Reasoning models require "developer" role instead of "system"
        if is_reasoning:
            messages = [
                {**m, "role": "developer"} if m["role"] == "system" else m
                for m in messages
            ]

        if use_native_ollama:
            payload: dict = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temp, "num_predict": mtok},
            }
            if response_format:
                payload["format"] = "json"
        else:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if not is_reasoning:
                payload["temperature"] = temp
            if self.provider == "openai":
                payload["max_completion_tokens"] = mtok
                if response_format:
                    payload["response_format"] = response_format
            else:
                payload["max_tokens"] = mtok
                if response_format:
                    # Together and others: use simpler json mode
                    payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                t0 = time.monotonic()
                async with _get_semaphore():
                    result = await self._stream_request(
                        url, headers, payload, use_native_ollama
                    )
                elapsed = time.monotonic() - t0

                self._call_count += 1
                elapsed_ms = elapsed * 1000
                self._total_latency_ms += elapsed_ms
                usage = result.get("usage", {})
                self._total_tokens += usage.get("total_tokens", 0)

                content = ""
                try:
                    content = result["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    pass

                logger.info(
                    "LLM call %d [%s/%s] %.1fs — tokens=%d, content_len=%d",
                    self._call_count, self.provider, self.model,
                    elapsed, usage.get("total_tokens", 0), len(content),
                )
                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status == 429 or status >= 500:
                    wait = 2 ** attempt
                    logger.warning(
                        "LLM call failed (attempt %d/%d, status %d), retrying in %ds",
                        attempt, self.max_retries, status, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "LLM connection error (attempt %d/%d), retrying in %ds: %s",
                    attempt, self.max_retries, wait, e,
                )
                await asyncio.sleep(wait)

        raise last_error  # type: ignore[misc]

    async def _stream_request(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict,
        native_ollama: bool,
    ) -> dict:
        """Send a streaming request and assemble the response."""
        content_parts: list[str] = []
        usage: dict = {}
        finish_reason = "stop"

        read_timeout = max(self.timeout, 300)
        timeout = httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue

                    if native_ollama:
                        chunk = json.loads(raw_line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            content_parts.append(token)
                        if chunk.get("done"):
                            prompt_tok = chunk.get("prompt_eval_count", 0)
                            comp_tok = chunk.get("eval_count", 0)
                            usage = {
                                "prompt_tokens": prompt_tok,
                                "completion_tokens": comp_tok,
                                "total_tokens": prompt_tok + comp_tok,
                            }
                    else:
                        line = raw_line
                        if line.startswith("data: "):
                            line = line[6:]
                        elif line.startswith("data:"):
                            line = line[5:]
                        else:
                            continue

                        if line.strip() == "[DONE]":
                            break

                        chunk = json.loads(line)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                content_parts.append(token)
                            if choices[0].get("finish_reason"):
                                finish_reason = choices[0]["finish_reason"]
                        if "usage" in chunk:
                            usage = chunk["usage"]

        return {
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "".join(content_parts)},
                "finish_reason": finish_reason,
            }],
            "usage": usage,
        }

    async def _anthropic_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> dict:
        """Chat completion via the Anthropic Messages API."""
        from anthropic import AsyncAnthropic

        temp = temperature if temperature is not None else self.temperature
        mtok = max_tokens if max_tokens is not None else self.max_tokens

        # Separate system message from conversation
        system_text = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                conv_messages.append(m)

        # If structured output requested, instruct via system prompt
        if response_format and system_text:
            system_text += "\nYou MUST respond with valid JSON only. No other text."

        client = AsyncAnthropic(api_key=self.api_key)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": mtok,
            "temperature": temp,
            "messages": conv_messages,
        }
        if system_text.strip():
            kwargs["system"] = system_text.strip()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                t0 = time.monotonic()
                async with _get_semaphore():
                    response = await client.messages.create(**kwargs)
                elapsed = time.monotonic() - t0

                self._call_count += 1
                self._total_latency_ms += elapsed * 1000

                content = ""
                for block in response.content:
                    if block.type == "text":
                        content += block.text

                usage_data = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": (
                        response.usage.input_tokens + response.usage.output_tokens
                    ),
                }
                self._total_tokens += usage_data["total_tokens"]

                logger.info(
                    "LLM call %d [anthropic/%s] %.1fs — tokens=%d, content_len=%d",
                    self._call_count, self.model, elapsed,
                    usage_data["total_tokens"], len(content),
                )

                return {
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": response.stop_reason or "stop",
                    }],
                    "usage": usage_data,
                }
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "Anthropic call failed (attempt %d/%d), retrying in %ds: %s",
                        attempt, self.max_retries, wait, e,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error  # type: ignore[misc]

    # --- Public convenience methods ---

    async def complete_text(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion and return the content string."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = await self._raw_chat(messages, temperature, max_tokens)
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Send a chat completion expecting JSON, return parsed dict.

        For OpenAI: uses structured output with json_schema response_format.
        For Anthropic: instructs JSON in system prompt.
        For Ollama/Together: uses json_object mode.

        Args:
            schema: JSON Schema dict. Used for OpenAI structured outputs.
                    Other providers get json_object mode + schema in prompt.
        """
        response_format = None
        extra_instruction = ""

        if schema:
            if self.provider == "openai":
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        "schema": schema,
                    },
                }
            else:
                # For non-OpenAI: include schema in prompt for guidance
                response_format = {"type": "json_object"}
                extra_instruction = (
                    f"\n\nRespond with JSON matching this schema:\n"
                    f"```json\n{json.dumps(schema, indent=2)}\n```"
                )
        else:
            response_format = {"type": "json_object"}

        full_system = system + extra_instruction if extra_instruction else system

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ]
        result = await self._raw_chat(
            messages, temperature, max_tokens, response_format
        )

        content = ""
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass

        # Parse JSON from content — handle markdown code blocks
        text = content.strip()
        if text.startswith("```"):
            # Strip ```json ... ``` wrapper
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        return json.loads(text)

    @property
    def stats(self) -> dict:
        """Return usage statistics for this client instance."""
        avg_latency = (
            round(self._total_latency_ms / self._call_count, 1)
            if self._call_count > 0
            else 0.0
        )
        return {
            "provider": self.provider,
            "model": self.model,
            "calls": self._call_count,
            "total_tokens": self._total_tokens,
            "total_latency_s": round(self._total_latency_ms / 1000, 2),
            "avg_latency_ms": avg_latency,
        }


# --- Factory functions ---

# Provider defaults: base_url and env var names
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "ollama": {
        "base_url_env": "OLLAMA_BASE_URL",
        "api_key_env": "OLLAMA_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
    },
}


def make_client(
    provider: str,
    model: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 3,
    timeout: int = 120,
) -> LLMClient:
    """Create an LLMClient for the given provider.

    Reads API keys and base URLs from environment variables.
    """
    defaults = _PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError(
            f"Unknown provider {provider!r}. "
            f"Available: {list(_PROVIDER_DEFAULTS.keys())}"
        )

    # Resolve base URL
    if "base_url_env" in defaults:
        base_url = os.getenv(defaults["base_url_env"], "")
        if not base_url:
            raise ValueError(
                f"Environment variable {defaults['base_url_env']} not set "
                f"for provider {provider!r}"
            )
    else:
        base_url = defaults["base_url"]

    # Auto-append /v1 for Ollama behind reverse proxy
    if provider == "ollama" and "/v1" not in base_url:
        base_url = base_url.rstrip("/") + "/v1"

    # Resolve API key
    api_key_env = defaults.get("api_key_env", "")
    api_key = os.getenv(api_key_env, "") if api_key_env else ""

    return LLMClient(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
        timeout=timeout,
    )


def make_client_from_config(config: dict) -> LLMClient:
    """Create an LLMClient from an injection_llm config dict.

    Expected keys: provider, model, and optionally temperature, max_tokens.

    Example config (from mt_backends.yaml):
        injection_llm:
          provider: "openai"
          model: "gpt-4.1"
          temperature: 0.3
          max_tokens: 4096
    """
    return make_client(
        provider=config["provider"],
        model=config["model"],
        temperature=config.get("temperature", 0.3),
        max_tokens=config.get("max_tokens", 4096),
    )
