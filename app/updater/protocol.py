"""Authenticated, bounded Unix IPC. No command strings or arbitrary paths."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import socket
import time
import uuid
from pathlib import Path

REPO = 'sagesaint84/wealth'
IMAGE = 'ghcr.io/' + REPO
SHA = re.compile(r'[a-f0-9]{40}\Z')
DIGEST = re.compile(r'sha256:[a-f0-9]{64}\Z')
MAX_FRAME = 65536
METHODS = {'status', 'check', 'install', 'confirm', 'cleanup_preview', 'cleanup'}


class UpdateError(Exception):
    """Only fixed, non-sensitive error codes cross the IPC/API boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def seal(value, key):
    return {'payload': value, 'mac': hmac.new(key, canonical(value), hashlib.sha256).hexdigest()}


def unseal(value, key):
    if not isinstance(value, dict) or set(value) != {'payload', 'mac'}:
        raise UpdateError('IPC_AUTH_FAILED')
    expected = hmac.new(key, canonical(value['payload']), hashlib.sha256).hexdigest()
    if not isinstance(value['mac'], str) or not hmac.compare_digest(value['mac'], expected):
        raise UpdateError('IPC_AUTH_FAILED')
    return value['payload']


def receive(stream):
    data = bytearray()
    while not data.endswith(b'\n'):
        part = stream.recv(min(4096, MAX_FRAME + 1 - len(data)))
        if not part:
            raise UpdateError('IPC_TRUNCATED')
        data.extend(part)
        if len(data) > MAX_FRAME:
            raise UpdateError('IPC_TOO_LARGE')
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError('IPC_INVALID') from exc


def validate_request(payload, now=None):
    if not isinstance(payload, dict) or set(payload) != {'method', 'args', 'actor', 'nonce', 'timestamp'}:
        raise UpdateError('IPC_INVALID')
    if not isinstance(payload['method'], str) or payload['method'] not in METHODS or not isinstance(payload['args'], dict):
        raise UpdateError('IPC_INVALID')
    if not isinstance(payload['actor'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', payload['actor']):
        raise UpdateError('IPC_INVALID')
    if not isinstance(payload['nonce'], str) or not re.fullmatch(r'[a-f0-9]{32}', payload['nonce']):
        raise UpdateError('IPC_INVALID')
    if type(payload['timestamp']) is not int or abs((time.time() if now is None else now) - payload['timestamp']) > 60:
        raise UpdateError('IPC_EXPIRED')
    args = payload['args']
    expected = {'install': {'sha', 'digest'}, 'confirm': {'job_id'}, 'cleanup': {'images'}}.get(payload['method'], set())
    if set(args) != expected:
        raise UpdateError('IPC_INVALID')
    if payload['method'] == 'install' and (not isinstance(args['sha'], str) or not SHA.fullmatch(args['sha']) or not isinstance(args['digest'], str) or not DIGEST.fullmatch(args['digest'])):
        raise UpdateError('TARGET_INVALID')
    if payload['method'] == 'confirm' and not re.fullmatch(r'[a-f0-9]{32}', str(args['job_id'])):
        raise UpdateError('JOB_INVALID')
    if payload['method'] == 'cleanup' and (not isinstance(args['images'], list) or len(args['images']) > 20 or not all(isinstance(i, str) and DIGEST.fullmatch(i) for i in args['images'])):
        raise UpdateError('IMAGE_INVALID')
    return payload


class HostClient:
    def __init__(self, directory='/run/wealth-updater'):
        self.directory = Path(directory)

    def call(self, method, args=None, actor='admin'):
        try:
            key = (self.directory / 'client.key').read_bytes()
            if len(key) != 32:
                raise UpdateError('UPDATER_NOT_INSTALLED')
            payload = {'method': method, 'args': args or {}, 'actor': actor,
                       'nonce': uuid.uuid4().hex, 'timestamp': int(time.time())}
            validate_request(payload)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(55)
                stream.connect(str(self.directory / 'worker.sock'))
                stream.sendall(canonical(seal(payload, key)) + b'\n')
                reply = unseal(receive(stream), key)
            if reply.get('nonce') != payload['nonce']:
                raise UpdateError('IPC_AUTH_FAILED')
            if not reply.get('ok'):
                raise UpdateError(reply.get('error', 'UPDATER_UNAVAILABLE'))
            return reply['result']
        except (OSError, ValueError, AttributeError) as exc:
            raise UpdateError('UPDATER_UNAVAILABLE') from exc
