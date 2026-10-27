"""Root-only, offline retirement of one proven missing rollback reference.

Not registered with IPC or the web API. Never invokes image/container mutations.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from .host import ACTIVE, DockerHost, Engine, atomic, exclusive
from .protocol import DIGEST, SHA, UpdateError, canonical

DIRECTORY = Path('/var/lib/wealth-updater')


def service_stopped():
    try:
        result = subprocess.run(['/usr/bin/systemctl', 'is-active', 'wealth-updater.service'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=10, check=False,
                                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    except (OSError, subprocess.SubprocessError):
        raise UpdateError('MAINTENANCE_SERVICE_UNCONFIRMED') from None
    if result.returncode != 3 or result.stdout.strip() != b'inactive':
        raise UpdateError('MAINTENANCE_SERVICE_NOT_STOPPED')


class MaintenanceDockerHost(DockerHost):
    def image_absent(self, image_id):
        if not isinstance(image_id, str) or not DIGEST.fullmatch(image_id):
            raise UpdateError('IMAGE_INVALID')
        # The normal command wrapper intentionally hides stderr. Here only the
        # daemon's exact missing-image response proves absence; errors do not.
        try:
            result = subprocess.run(['/usr/bin/docker', 'image', 'inspect', image_id],
                                    cwd=self.root, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=30, check=False,
                                    env={'PATH': '/usr/bin:/bin', 'HOME': '/root',
                                         'LC_ALL': 'C', 'DOCKER_CONFIG': '/etc/wealth-updater/docker'})
        except (OSError, subprocess.SubprocessError):
            raise UpdateError('MAINTENANCE_IMAGE_UNCONFIRMED') from None
        if result.returncode == 0:
            return False
        if (result.returncode == 1 and result.stdout.strip() == b'[]'
                and result.stderr.strip() == ('Error response from daemon: No such image: ' + image_id).encode()):
            return True
        raise UpdateError('MAINTENANCE_IMAGE_UNCONFIRMED')


def validate_expected(expected):
    if set(expected) != {'current', 'rollback', 'job_id'} or not isinstance(expected['job_id'], str) or not re.fullmatch(r'[a-f0-9]{32}', expected['job_id']):
        raise UpdateError('MAINTENANCE_EXPECTATION_INVALID')
    for key in ('current', 'rollback'):
        value = expected[key]
        if (not isinstance(value, dict) or set(value) != {'sha', 'digest', 'image_id'}
                or any(not isinstance(value[k], str) for k in value)
                or not SHA.fullmatch(value['sha']) or not DIGEST.fullmatch(value['digest'])
                or not DIGEST.fullmatch(value['image_id'])):
            raise UpdateError('MAINTENANCE_EXPECTATION_INVALID')
    if expected['current']['image_id'] == expected['rollback']['image_id']:
        raise UpdateError('MAINTENANCE_CURRENT_PROTECTED')


def audit(engine, expected):
    validate_expected(expected)
    state = engine.state
    if (type(state.get('version')) is not int or state['version'] != 1
            or not isinstance(state.get('jobs'), list) or not isinstance(state.get('managed'), list)
            or not isinstance(state.get('nonces'), dict) or state.get('rollback') != expected['rollback']):
        raise UpdateError('MAINTENANCE_REFERENCE_CHANGED')
    terminal = {'succeeded', 'failed', 'interrupted', 'rolled_back'}
    if any(not isinstance(j, dict) or j.get('stage') in ACTIVE or j.get('stage') not in terminal for j in state['jobs']):
        raise UpdateError('MAINTENANCE_JOB_LOCKED')
    installs = [j for j in state['jobs'] if j.get('kind') == 'install']
    if not installs:
        raise UpdateError('MAINTENANCE_INSTALL_UNCONFIRMED')
    job = installs[-1]
    if (job.get('id') != expected['job_id'] or job.get('stage') != 'succeeded'
            or job.get('confirmed') is not True or job.get('may_have_replaced') is not True
            or 'error' in job or 'rollback_result' in job
            or any(job.get(k) != v for k, v in expected['current'].items())
            or not isinstance(job.get('baseline'), dict)
            or any(job['baseline'].get(k) != v for k, v in expected['rollback'].items())
            or any(v['image_id'] not in state['managed'] for v in (expected['current'], expected['rollback']))):
        raise UpdateError('MAINTENANCE_INSTALL_UNCONFIRMED')
    current = engine.driver.snapshot()  # existing Compose/mount/running/OCI checks
    if any(current.get(k) != job['baseline'].get(k) for k in ('project', 'mounts', 'files', 'others')):
        raise UpdateError('MAINTENANCE_INSTALL_UNCONFIRMED')
    if any(current.get(k) != v for k, v in expected['current'].items()) or current.get('restarts') != 0 or not engine.driver.healthy():
        raise UpdateError('MAINTENANCE_CURRENT_UNCONFIRMED')
    containers = engine.driver.containers()  # all, including stopped containers
    if not containers or not any(c['image'] == expected['current']['image_id'] for c in containers):
        raise UpdateError('MAINTENANCE_CURRENT_UNCONFIRMED')
    if any(c['image'] == expected['rollback']['image_id'] for c in containers):
        raise UpdateError('MAINTENANCE_IMAGE_REFERENCED')
    if not engine.driver.image_absent(expected['rollback']['image_id']):
        raise UpdateError('MAINTENANCE_IMAGE_PRESENT')
    return {'current': current, 'containers': containers}


def retire(engine, expected, *, apply=False, stopped=service_stopped):
    """Caller owns worker.lock; no startup recovery or IPC dispatch is involved."""
    with engine.mutex:
        raw = engine.path.read_bytes()
        before = copy.deepcopy(engine.state)
        if json.loads(raw) != before:
            raise UpdateError('MAINTENANCE_STATE_CHANGED')
        stopped()
        baseline = audit(engine, expected)
        result = {'action': 'dry-run', 'rollback_image_exists': False,
                  'automatic_rollback_available': False, 'changed': False}
        if not apply:
            stopped()
            if audit(engine, expected) != baseline or engine.path.read_bytes() != raw:
                raise UpdateError('MAINTENANCE_PREFLIGHT_CHANGED')
            return result
        backup = engine.directory / ('rollback-retire-' + uuid.uuid4().hex + '.json')
        if backup.exists():
            raise UpdateError('MAINTENANCE_BACKUP_EXISTS')
        atomic(backup, raw)  # durable original bytes, before changing state
        if backup.read_bytes() != raw:
            raise UpdateError('MAINTENANCE_BACKUP_FAILED')
        stopped()
        if audit(engine, expected) != baseline or engine.path.read_bytes() != raw:
            raise UpdateError('MAINTENANCE_PREFLIGHT_CHANGED')
        updated = copy.deepcopy(before)
        updated['rollback'] = None
        try:
            engine.state = updated
            engine.save()  # unchanged atomic/fsync persistence contract
            stopped()
            if engine.path.read_bytes() != canonical(updated):
                raise UpdateError('MAINTENANCE_SAVE_UNCONFIRMED')
            if (engine.driver.snapshot() != baseline['current']
                    or engine.driver.containers() != baseline['containers']
                    or not engine.driver.image_absent(expected['rollback']['image_id'])):
                raise UpdateError('MAINTENANCE_POSTFLIGHT_CHANGED')
        except Exception:
            engine.state = before
            try:
                atomic(engine.path, raw)
                if engine.path.read_bytes() != raw:
                    raise OSError('restore unconfirmed')
            except Exception:
                raise UpdateError('MAINTENANCE_RESTORE_REQUIRED') from None
            raise UpdateError('MAINTENANCE_ABORTED_STATE_RESTORED') from None
        return {**result, 'action': 'retired', 'changed': True, 'backup': str(backup)}


def secure_path(path, directory=False, private=True):
    info = path.lstat()
    if (info.st_uid != 0 or info.st_mode & (0o077 if private else 0o022)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise UpdateError('MAINTENANCE_PATH_UNSAFE')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Root-only offline missing rollback reference retirement')
    for group in ('current', 'rollback'):
        for field in ('sha', 'digest', 'image-id'):
            parser.add_argument('--expect-' + group + '-' + field, required=True)
    parser.add_argument('--expect-install-job', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-forget-missing-rollback', action='store_true')
    options = parser.parse_args(argv)
    if os.name != 'posix' or os.geteuid() != 0:
        raise UpdateError('MAINTENANCE_ROOT_REQUIRED')
    if options.apply != options.confirm_forget_missing_rollback:
        raise UpdateError('MAINTENANCE_CONFIRMATION_REQUIRED')
    expected = {key: {field: getattr(options, 'expect_' + key + '_' + field) for field in ('sha', 'digest', 'image_id')}
                for key in ('current', 'rollback')}
    expected['job_id'] = options.expect_install_job
    validate_expected(expected)
    secure_path(DIRECTORY, directory=True)
    secure_path(DIRECTORY / 'state.json')
    lock = DIRECTORY / 'worker.lock'
    if lock.exists() or lock.is_symlink():
        secure_path(lock, private=False)
    service_stopped()
    with exclusive(lock):
        service_stopped()
        # Default Engine construction must still recover; only this offline
        # entry point opts out so active/failed jobs are rejected, never run.
        engine = Engine(MaintenanceDockerHost(), None, DIRECTORY, recover=False)
        print(json.dumps(retire(engine, expected, apply=options.apply, stopped=service_stopped), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (UpdateError, OSError, ValueError, KeyError, TypeError) as exc:
        print(exc.code if isinstance(exc, UpdateError) else 'MAINTENANCE_FAILED')
        raise SystemExit(1)
