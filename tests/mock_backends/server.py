#!/usr/bin/env python3
"""OpenAI-compatible mock LLM backend for Token Factory demos."""

from __future__ import annotations

import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Token Factory Mock Backend")
ROLE = os.environ.get("MOCK_ROLE", "general")
MODEL = os.environ.get("MOCK_MODEL", f"mock/{ROLE}-v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "role": ROLE}


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": MODEL, "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    messages = body.get("messages", [])
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    content = (
        f"[mock-{ROLE}] Processed: {user[:200]}"
        if ROLE != "coding"
        else f"[mock-coding] ```python\n# echo: {user[:120]}\nprint('ok')\n```"
    )
    if body.get("stream"):
        return JSONResponse({"error": "streaming not implemented in mock"}, status_code=400)
    return JSONResponse(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", MODEL),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
