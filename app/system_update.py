"""Admin-only web boundary. No Docker subprocess/socket/host credentials here."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.updater.protocol import HostClient, UpdateError

client = HostClient()
logger = logging.getLogger(__name__)


class RateLimit:
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    def take(self, actor, action, limit):
        with self.lock:
            now = time.monotonic()
            self.entries = {key: [t for t in values if now - t < 60] for key, values in self.entries.items() if values and now - values[-1] < 60}
            key = (actor, action)
            values = self.entries.setdefault(key, [])
            if len(values) >= limit:
                raise HTTPException(429, detail={'code': 'UPDATE_RATE_LIMIT'})
            values.append(now)


def register_update_routes(app, *, app_version, secret, role, username, origin):
    signer = URLSafeTimedSerializer(secret, salt='wealth-system-update-csrf-v1')
    limiter = RateLimit()

    @app.middleware('http')
    async def prevent_update_caching(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/system-update/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Vary'] = 'Cookie'
        return response

    def identity(request):
        name = username(request)
        if role(request) != 'admin' or getattr(request.state, 'must_change_password', False):
            raise HTTPException(403, detail={'code': 'ADMIN_REQUIRED'})
        actor = str(getattr(request.state, 'user_id', None) or hashlib.sha256(name.encode()).hexdigest())
        return name, actor

    def csrf_context(request, actor):
        return {'actor': actor, 'session': hashlib.sha256(request.cookies.get('dashboard_session_v2', '').encode()).hexdigest()}

    async def rpc(method, actor, args=None):
        try:
            return await asyncio.to_thread(client.call, method, args, actor)
        except UpdateError as exc:
            raise HTTPException(503 if method in {'check', 'status'} else 409, detail={'code': exc.code}) from None

    @app.get('/api/system-update/status')
    async def status(request: Request):
        _, actor = identity(request)
        limiter.take(actor, 'status', 60)
        base = {'app_version': app_version, 'csrf_token': signer.dumps(csrf_context(request, actor))}
        try:
            return {**base, 'host_available': True, **await rpc('status', actor)}
        except HTTPException as exc:
            return {**base, 'host_available': False, 'error': exc.detail['code'], 'jobs': []}

    @app.get('/api/system-update/check')
    async def check(request: Request):
        _, actor = identity(request)
        limiter.take(actor, 'check', 3)
        return await rpc('check', actor)

    @app.get('/api/system-update/cleanup-preview')
    async def cleanup_preview(request: Request):
        _, actor = identity(request)
        limiter.take(actor, 'preview', 5)
        return await rpc('cleanup_preview', actor)

    async def authorize(request, expected):
        name, actor = identity(request)
        if not origin(request):
            raise HTTPException(403, detail={'code': 'UPDATE_ORIGIN_FORBIDDEN'})
        token = request.headers.get('x-wealth-update-csrf', '')
        try:
            if signer.loads(token, max_age=600) != csrf_context(request, actor):
                raise BadSignature('context')
        except BadSignature:
            raise HTTPException(403, detail={'code': 'UPDATE_CSRF_INVALID'}) from None
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, detail={'code': 'JSON_REQUIRED'})
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                raise HTTPException(413, detail={'code': 'UPDATE_BODY_TOO_LARGE'})
        import json
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise HTTPException(400, detail={'code': 'UPDATE_BODY_INVALID'}) from None
        if not isinstance(body, dict) or set(body) != expected | {'password', 'confirm'} or body['confirm'] is not True or not isinstance(body['password'], str) or not 1 <= len(body['password']) <= 256:
            raise HTTPException(400, detail={'code': 'UPDATE_BODY_INVALID'})
        limiter.take(actor, 'reauth', 5)
        from app.services.user_manager import authenticate_user
        user = await asyncio.to_thread(authenticate_user, name, body.pop('password'))
        if not user or user.get('role') != 'admin' or user.get('must_change_password'):
            logger.warning('system_update REAUTH_FAILED actor=%s', actor)
            raise HTTPException(403, detail={'code': 'UPDATE_REAUTH_FAILED'})
        body.pop('confirm')
        # Strict host protocol validates target digests/IDs again before any work.
        logger.info('system_update AUTHORIZED actor=%s action=%s', actor, request.url.path.rsplit('/', 1)[-1])
        return actor, body

    @app.post('/api/system-update/install', status_code=202)
    async def install(request: Request):
        actor, args = await authorize(request, {'sha', 'digest'})
        return await rpc('install', actor, args)

    @app.post('/api/system-update/confirm')
    async def confirm(request: Request):
        actor, args = await authorize(request, {'job_id'})
        return await rpc('confirm', actor, args)

    @app.post('/api/system-update/cleanup', status_code=202)
    async def cleanup(request: Request):
        actor, args = await authorize(request, {'images'})
        return await rpc('cleanup', actor, args)
