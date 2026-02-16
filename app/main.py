from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

from app.config import get_settings
from app.di import build_telegram_application
from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    settings = get_settings()
    application = build_telegram_application()
    app_instance.state.telegram_application = application
    await application.initialize()
    await application.start()
    logger.info(json.dumps({'event': 'startup', 'status': 'ok', 'env': settings.ENV}))
    try:
        yield
    finally:
        await application.stop()
        await application.shutdown()
        logger.info(json.dumps({'event': 'shutdown', 'status': 'ok'}))


app = FastAPI(title='botyara', version='2.0-fixed', lifespan=lifespan)


@app.middleware('http')
async def logging_middleware(request: Request, call_next):
    trace_id = request.headers.get('x-cloud-trace-context', str(uuid.uuid4()))
    response = await call_next(request)
    logger.info(
        json.dumps(
            {
                'event': 'http_request',
                'path': request.url.path,
                'method': request.method,
                'status_code': response.status_code,
                'trace_id': trace_id,
            }
        )
    )
    response.headers['x-trace-id'] = trace_id
    return response


@app.get('/healthz')
async def healthz() -> dict[str, str | bool]:
    return {'ok': True, 'version': '2.0-fixed'}


@app.get('/')
async def root() -> dict[str, str]:
    return {'service': 'botyara'}


@app.post('/webhook')
async def webhook(request: Request) -> dict[str, bool]:
    settings = get_settings()
    if settings.WEBHOOK_SECRET:
        header_secret = request.headers.get('x-telegram-bot-api-secret-token')
        if header_secret != settings.WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail='invalid webhook secret')

    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover
        logger.warning(json.dumps({'event': 'webhook_invalid_json', 'error': str(exc)}))
        return {'ok': True}

    application = request.app.state.telegram_application
    update = Update.de_json(payload, application.bot)

    logger.info(
        json.dumps(
            {
                'event': 'webhook_update',
                'update_id': payload.get('update_id'),
                'user_id': payload.get('message', {}).get('from', {}).get('id'),
                'chat_id': payload.get('message', {}).get('chat', {}).get('id'),
                'state': 'received',
                'action': 'process_update',
            },
            ensure_ascii=False,
        )
    )
    await application.process_update(update)
    return {'ok': True}
