"""Persisted capability boundary. No Docker subprocess/socket/host credentials."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
import secrets

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.updater.protocol import HostClient, UpdateError
from app.services.update_permissions import can_system_update

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


def register_update_routes(app, *, app_version, secret, username, origin, session_current):
    signer = URLSafeTimedSerializer(secret, salt='wealth-system-update-csrf-v1')
    limiter = RateLimit()
    approvals = URLSafeTimedSerializer(secret, salt='wealth-update-approval-' + secrets.token_hex(16))
    used = {}
    approval_lock = threading.Lock()

    @app.middleware('http')
    async def prevent_update_caching(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(('/api/system-update/', '/api/admin/system-update-permissions/')):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Vary'] = 'Cookie'
        return response

    def identity(request, admin_only=False):
        name = username(request)
        from app.services.user_manager import get_user_by_name
        user = get_user_by_name(name)
        if not can_system_update(user) or admin_only and user.get('role') != 'admin':
            raise HTTPException(403, detail={'code': 'SYSTEM_UPDATE_FORBIDDEN'})
        actor = user['id']
        if actor != getattr(request.state, 'user_id', None):
            raise HTTPException(403, detail={'code': 'SYSTEM_UPDATE_FORBIDDEN'})
        if not session_current(request, user):
            raise HTTPException(401, detail={'code': 'UPDATE_SESSION_REFRESH_REQUIRED'})
        return name, actor, user

    def csrf_context(request, actor):
        _, current, user = identity(request)
        if actor != current:
            raise HTTPException(403, detail={'code': 'SYSTEM_UPDATE_FORBIDDEN'})
        return {'actor': actor, 'session': hashlib.sha256(request.cookies.get('dashboard_session_v2', '').encode()).hexdigest(),
                'epoch': user.get('system_update_epoch', '')}

    def issue(request, actor, kind, resource):
        return approvals.dumps({'context': csrf_context(request, actor), 'kind': kind,
                                'resource': resource, 'nonce': secrets.token_hex(16)})

    def consume(request, actor, token, kind, resource):
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise HTTPException(403, detail={'code': 'UPDATE_APPROVAL_INVALID'})
        try:
            value = approvals.loads(token, max_age=300)
            if value.get('context') != csrf_context(request, actor) or value.get('kind') != kind or value.get('resource') != resource:
                raise BadSignature('context')
            with approval_lock:
                now = time.monotonic()
                for nonce in list(used):
                    if now - used[nonce] > 300:
                        del used[nonce]
                if value['nonce'] in used:
                    raise BadSignature('replay')
                used[value['nonce']] = now
        except (BadSignature, KeyError, TypeError):
            raise HTTPException(403, detail={'code': 'UPDATE_APPROVAL_INVALID'}) from None

    async def rpc(method, actor, args=None):
        try:
            return await asyncio.to_thread(client.call, method, args, actor)
        except UpdateError as exc:
            raise HTTPException(503 if method in {'check', 'status'} else 409, detail={'code': exc.code}) from None

    @app.get('/api/system-update/status')
    async def status(request: Request):
        _, actor, _ = identity(request)
        limiter.take(actor, 'status', 60)
        base = {'app_version': app_version, 'csrf_token': signer.dumps(csrf_context(request, actor)),
                'operation_token': issue(request, actor, 'operation', {})}
        try:
            return {**base, 'host_available': True, **await rpc('status', actor)}
        except HTTPException as exc:
            return {**base, 'host_available': False, 'error': exc.detail['code'], 'jobs': []}

    @app.get('/api/system-update/check')
    async def check(request: Request):
        _, actor, _ = identity(request)
        limiter.take(actor, 'check', 3)
        return await rpc('check', actor)

    @app.get('/api/system-update/cleanup-preview')
    async def cleanup_preview(request: Request):
        _, actor, _ = identity(request)
        limiter.take(actor, 'preview', 5)
        result = await rpc('cleanup_preview', actor)
        return {**result, 'preview_token': issue(request, actor, 'cleanup', {'images': result['images']})}

    async def authorize(request, expected, *, reauthenticate, admin_only=False):
        name, actor, _ = identity(request, admin_only)
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
        fields = expected | ({'password', 'confirm'} if reauthenticate else {'confirm'})
        if not isinstance(body, dict) or set(body) != fields or body.get('confirm') is not True or (reauthenticate and (not isinstance(body.get('password'), str) or not 1 <= len(body['password']) <= 256)):
            raise HTTPException(400, detail={'code': 'UPDATE_BODY_INVALID'})
        if not reauthenticate:
            limiter.take(actor, 'operation', 5)
            consume(request, actor, request.headers.get('x-wealth-update-approval'), 'operation', {})
            _, current, fresh = identity(request)
            if current != actor:
                raise HTTPException(403, detail={'code': 'SYSTEM_UPDATE_FORBIDDEN'})
            body.pop('confirm')
            logger.info('system_update SESSION_AUTHORIZED actor=%s action=%s', actor, request.url.path.rsplit('/', 1)[-1])
            return actor, body, fresh
        limiter.take(actor, 'reauth', 5)
        from app.services.user_manager import authenticate_user
        user = await asyncio.to_thread(authenticate_user, name, body.pop('password'))
        if not user or user.get('id') != actor or not can_system_update(user) or admin_only and user.get('role') != 'admin':
            logger.warning('system_update REAUTH_FAILED actor=%s', actor)
            raise HTTPException(403, detail={'code': 'UPDATE_REAUTH_FAILED'})
        body.pop('confirm')
        _, current, fresh = identity(request, admin_only)
        if current != actor or (fresh.get('salt'), fresh.get('password_hash')) != (user.get('salt'), user.get('password_hash')):
            raise HTTPException(403, detail={'code': 'UPDATE_REAUTH_FAILED'})
        # Strict host protocol validates target digests/IDs again before any work.
        logger.info('system_update AUTHORIZED actor=%s action=%s', actor, request.url.path.rsplit('/', 1)[-1])
        return actor, body, user

    async def authorize_operation(request, expected):
        return await authorize(request, expected, reauthenticate=False)

    async def authorize_permission(request, expected):
        return await authorize(request, expected, reauthenticate=True, admin_only=True)

    @app.post('/api/system-update/install', status_code=202)
    async def install(request: Request):
        actor, args, _ = await authorize_operation(request, {'sha', 'digest'})
        return await rpc('install', actor, args)

    @app.post('/api/system-update/confirm')
    async def confirm(request: Request):
        actor, args, _ = await authorize_operation(request, {'job_id'})
        return await rpc('confirm', actor, args)

    @app.post('/api/system-update/cleanup', status_code=202)
    async def cleanup(request: Request):
        actor, args, _ = await authorize_operation(request, {'images', 'preview_token'})
        consume(request, actor, args.pop('preview_token'), 'cleanup', args)
        return await rpc('cleanup', actor, args)

    @app.get('/api/admin/system-update-permissions/challenge')
    async def permission_challenge(request: Request, target_id: str, enabled: bool):
        _, actor, _ = identity(request, admin_only=True)
        limiter.take(actor, 'permission_challenge', 20)
        from app.services.user_identity import validate_user_id
        try:
            target_id = validate_user_id(target_id)
        except (ValueError, TypeError):
            raise HTTPException(400, detail={'code': 'PERMISSION_TARGET_INVALID'}) from None
        return {'csrf_token': signer.dumps(csrf_context(request, actor)),
                'intent_token': issue(request, actor, 'permission', {'target_id': target_id, 'enabled': enabled})}

    @app.post('/api/admin/users/{target_id}/system-update')
    async def permission_change(request: Request, target_id: str):
        actor, args, user = await authorize_permission(request, {'enabled', 'intent_token'})
        from app.services.user_identity import validate_user_id
        from app.services.user_manager import set_system_update_permission
        try:
            target_id = validate_user_id(target_id)
            if type(args['enabled']) is not bool:
                raise ValueError('PERMISSION_INVALID')
            consume(request, actor, args['intent_token'], 'permission', {'target_id': target_id, 'enabled': args['enabled']})
            return await asyncio.to_thread(set_system_update_permission, actor, target_id, args['enabled'],
                credentials=(user.get('salt', ''), user.get('password_hash', '')))
        except ValueError as exc:
            known = {'ADMIN_REQUIRED', 'UPDATE_REAUTH_FAILED', 'PERMISSION_INVALID', 'PERMISSION_TARGET_INVALID', 'PERMISSION_TARGET_INACTIVE'}
            raise HTTPException(400, detail={'code': str(exc) if str(exc) in known else 'PERMISSION_TARGET_INVALID'}) from None
