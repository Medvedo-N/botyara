from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application

from app.bot.router import register_handlers
from app.config import BOT_TOKEN, VERSION
from app.logging_setup import setup_logging

logger = setup_logging()
app = FastAPI(title="botyara", version=VERSION)

telegram_app: Application | None = None


class TTLDeduplicator:
    def __init__(self, ttl_seconds: int = 600, max_size: int = 5000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._seen: OrderedDict[str, float] = OrderedDict()

    def seen(self, key: str) -> bool:
        now = time.time()
        self._purge(now)
        if key in self._seen:
            return True
        self._seen[key] = now
        if len(self._seen) > self.max_size:
            self._seen.popitem(last=False)
        return False

    def _purge(self, now: float) -> None:
        while self._seen:
            first_key = next(iter(self._seen))
            if now - self._seen[first_key] <= self.ttl_seconds:
                break
            self._seen.popitem(last=False)


update_deduplicator = TTLDeduplicator(ttl_seconds=600, max_size=5000)
operation_deduplicator = TTLDeduplicator(ttl_seconds=900, max_size=10000)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            ensure_ascii=False,
        )
    )
    return response


def _extract_op_id(payload: dict[str, Any]) -> str | None:
    direct = payload.get("op_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    callback_data = payload.get("callback_query", {}).get("data")
    if isinstance(callback_data, str) and callback_data:
        try:
            as_json = json.loads(callback_data)
            op = as_json.get("op_id")
            if isinstance(op, str) and op.strip():
                return op.strip()
        except Exception:
            match = re.search(r"op_id[:=]([A-Za-z0-9_-]+)", callback_data)
            if match:
                return match.group(1)

    text = payload.get("message", {}).get("text")
    if isinstance(text, str):
        match = re.search(r"op_id[:=]([A-Za-z0-9_-]+)", text)
        if match:
            return match.group(1)

    return None


def _extract_tg_id(payload: dict[str, Any]) -> int | None:
    message_user_id = payload.get("message", {}).get("from", {}).get("id")
    if isinstance(message_user_id, int):
        return message_user_id

    callback_user_id = payload.get("callback_query", {}).get("from", {}).get("id")
    if isinstance(callback_user_id, int):
        return callback_user_id

    return None


@app.on_event("startup")
async def startup_event():
    global telegram_app

    if not BOT_TOKEN:
        logger.warning(json.dumps({"event": "startup", "warning": "BOT_TOKEN is empty"}))
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(telegram_app)

    await telegram_app.initialize()
    logger.info(json.dumps({"event": "startup", "status": "telegram_initialized"}))


@app.get("/")
async def root():
    return {"status": "ok", "version": VERSION}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": VERSION}


@app.post("/webhook")
async def webhook(request: Request):
    update_id = None
    op_id = None
    tg_id = None
    try:
        data = await request.json()
        if not isinstance(data, dict):
            logger.error(json.dumps({"event": "invalid_webhook_payload", "reason": "payload_is_not_json_object"}))
            return JSONResponse({"ok": True, "handled_error": True})

        update_id = data.get("update_id")
        op_id = _extract_op_id(data)
        tg_id = _extract_tg_id(data)

        if isinstance(update_id, int) and update_deduplicator.seen(f"u:{update_id}"):
            logger.info(json.dumps({"event": "duplicate_update", "update_id": update_id, "tg_id": tg_id, "op_id": op_id}))
            return {"ok": True, "duplicate": True}

        if op_id and operation_deduplicator.seen(f"op:{op_id}"):
            logger.info(json.dumps({"event": "duplicate_operation", "update_id": update_id, "tg_id": tg_id, "op_id": op_id}))
            return {"ok": True, "duplicate_op": True}

        if telegram_app is None:
            logger.error(json.dumps({"event": "webhook", "error": "telegram_app_not_initialized", "update_id": update_id, "tg_id": tg_id, "op_id": op_id}))
            return JSONResponse({"ok": True, "warning": "telegram_app_not_initialized"})

        update = Update.de_json(data, telegram_app.bot)
        logger.info(
            json.dumps(
                {
                    "event": "telegram_update",
                    "update_id": update_id,
                    "message_id": update.message.message_id if update.message else None,
                    "callback_query_id": update.callback_query.id if update.callback_query else None,
                    "tg_id": tg_id,
                    "op_id": op_id,
                }
            )
        )
        await telegram_app.process_update(update)
        return {"ok": True}
    except Exception as exc:
        logger.exception(
            json.dumps(
                {
                    "event": "webhook_exception",
                    "error": str(exc),
                    "update_id": update_id,
                    "tg_id": tg_id,
                    "op_id": op_id,
                }
            )
        )
        return JSONResponse({"ok": True, "handled_error": True})
