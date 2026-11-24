"""Thin client for the local Ollama server.

`stream_chat` is an async generator yielding text chunks. The FastAPI app gets it
through a dependency (`get_llm`), so tests can swap in a fake with no Ollama running.
"""
import json
from typing import AsyncIterator

import httpx

from .config import settings


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    payload = {"model": settings.model, "messages": messages, "stream": True}
    # Pi inference is slow: long read timeout, short connect timeout.
    timeout = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=timeout) as client:
        async with client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break


async def ollama_alive() -> bool:
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=2.0) as client:
            return (await client.get("/api/tags")).status_code == 200
    except httpx.HTTPError:
        return False
