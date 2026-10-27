"""Oracle-only executor. Fixed Docker argv, durable jobs, automatic rollback.

The FastAPI app imports protocol only. This module runs as a separately installed
systemd service; Docker access is intentionally restricted to this host boundary.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import socketserver
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .protocol import IMAGE, DIGEST, UpdateError, canonical, receive, seal, unseal, validate_request
from .releases import ReleaseVerifier, NoRedirect

ACTIVE = {'queued', 'checking', 'pulling', 'replacing', 'verifying', 'rolling_back', 'cleaning'}


def atomic(path, value):
    """State and pin file are root-owned; fsync before any Docker replacement."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'wb') as stream:
        os.chmod(tmp, 0o600)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    if os.name != 'nt':
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@contextlib.contextmanager
def exclusive(path):
    """Cross-process single owner, including recovery after a host restart."""
    with open(path, 'a+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise UpdateError('WORKER_ALREADY_RUNNING') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class DockerHost:
    """No shell, browser args, arbitrary container names or delete paths."""
    def __init__(self, root=Path('/docker/wealth'), state=Path('/var/lib/wealth-updater'), sleep=time.sleep):
        self.root, self.state, self.sleep = Path(root), Path(state), sleep
        self.files = [self.root / n for n in ('docker-compose.ghcr.yml', 'docker-compose.override.yml', 'docker-compose.updater.yml')]
        self.pin = self.state / 'pin.yml'

    def command(self, args, timeout=30):
        try:
            result = subprocess.run(['/usr/bin/docker', *args], cwd=self.root,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=True,
                                    env={'PATH': '/usr/bin:/bin', 'HOME': '/root', 'DOCKER_CONFIG': '/etc/wealth-updater/docker'})
            if len(result.stdout) > 8_000_000:
                raise UpdateError('DOCKER_OUTPUT_LIMIT')
            return result.stdout.decode()
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise UpdateError('DOCKER_COMMAND_FAILED') from None

    def snapshot(self):
        item = json.loads(self.command(['inspect', 'wealth']))[0]
        config, labels = item['Config'], item['Config'].get('Labels') or {}
        files = labels.get('com.docker.compose.project.config_files', '').split(',')
        expected = [str(p) for p in self.files]
        if files not in (expected, expected + [str(self.pin)]) or labels.get('com.docker.compose.service') != 'dashboard' or labels.get('com.docker.compose.project.working_dir') != str(self.root):
            raise UpdateError('COMPOSE_MISMATCH')
        project = labels.get('com.docker.compose.project', '')
        import re
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', project):
            raise UpdateError('COMPOSE_MISMATCH')
        mounts = sorted([{k: m[k] for k in ('Type', 'Source', 'Destination', 'RW')} for m in item['Mounts']], key=lambda m: m['Destination'])
        required = [('/app/data', self.root / 'data', True),
                    ('/opt/toss-wts/tossctl', self.root / 'toss-wts/bin/tossctl', False),
                    ('/opt/toss-wts/config', self.root / 'toss-wts/config', True),
                    ('/run/wealth-updater', Path('/run/wealth-updater'), False)]
        by_destination = {m['Destination']: m for m in mounts}
        for destination, source, rw in required:
            m = by_destination.get(destination)
            if not m or (m['Source'], m['RW'], m['Type']) != (str(source), rw, 'bind'):
                raise UpdateError('MOUNT_MISMATCH')
        if any(m['Destination'].endswith('docker.sock') for m in mounts):
            raise UpdateError('DOCKER_SOCKET_FORBIDDEN')
        image = self.inspect_image(item['Image'])
        refs = [r for r in image.get('RepoDigests', []) if r.startswith(IMAGE + '@')]
        revision = (image.get('Config', {}).get('Labels') or {}).get('org.opencontainers.image.revision')
        from .protocol import SHA
        if len(refs) != 1 or not DIGEST.fullmatch(refs[0].split('@')[1]) or not isinstance(revision, str) or not SHA.fullmatch(revision):
            raise UpdateError('CURRENT_IMAGE_UNCONFIRMED')
        if not item['State']['Running']:
            raise UpdateError('CURRENT_NOT_RUNNING')
        return {'image_id': item['Image'], 'digest': refs[0].split('@')[1], 'sha': revision,
                'project': project, 'mounts': mounts, 'restarts': item['RestartCount'],
                'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.files},
                'others': self.containers(exclude_wealth=True)}

    def inspect_image(self, ref):
        if not (DIGEST.fullmatch(ref) or ref.startswith(IMAGE + '@') and DIGEST.fullmatch(ref[len(IMAGE)+1:])):
            raise UpdateError('IMAGE_INVALID')
        return json.loads(self.command(['image', 'inspect', ref]))[0]

    def containers(self, exclude_wealth=False):
        rows = self.command(['ps', '-aq']).split()
        if not rows:
            return []
        items = json.loads(self.command(['inspect', *rows]))
        return sorted([{'id': c['Id'], 'image': c['Image']} for c in items if not exclude_wealth or c['Name'] != '/wealth'], key=lambda c: c['id'])

    def free_bytes(self):
        root = self.command(['info', '--format', '{{.DockerRootDir}}']).strip()
        return shutil.disk_usage(root).free

    def healthy(self):
        opener = urllib.request.build_opener(NoRedirect())
        try:
            opener.open('http://127.0.0.1:4829/', timeout=3).close()
            return False
        except urllib.error.HTTPError as exc:
            if exc.code != 307:
                return False
        except OSError:
            return False
        try:
            for asset in ('wealth.js', 'wealth-layout.css'):
                request = urllib.request.Request('http://127.0.0.1:4829/static/' + asset, headers={'Accept-Encoding': 'gzip'})
                with opener.open(request, timeout=3) as response:
                    if response.status != 200 or response.headers.get('Content-Encoding') != 'gzip':
                        return False
            return True
        except (OSError, urllib.error.HTTPError):
            return False

    def pull(self, digest):
        if not DIGEST.fullmatch(digest):
            raise UpdateError('TARGET_INVALID')
        self.command(['pull', IMAGE + '@' + digest], timeout=600)
        image = self.inspect_image(IMAGE + '@' + digest)
        if IMAGE + '@' + digest not in image.get('RepoDigests', []):
            raise UpdateError('PULLED_DIGEST_MISMATCH')
        return image['Id']

    def replace(self, reference, baseline):
        if not (DIGEST.fullmatch(reference) or reference.startswith(IMAGE + '@') and DIGEST.fullmatch(reference[len(IMAGE)+1:])):
            raise UpdateError('TARGET_INVALID')
        atomic(self.pin, f'services:\n  dashboard:\n    image: {reference}\n'.encode())
        args = ['compose', '-p', baseline['project']]
        for p in [*self.files, self.pin]:
            args.extend(['-f', str(p)])
        self.command(args + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', 'dashboard'], timeout=120)

    def verify(self, image_id, baseline):
        # Three consecutive checks ensure a restart loop is not accepted.
        stable = 0
        for _ in range(30):
            try:
                current = self.snapshot()
                if current['mounts'] != baseline['mounts'] or current['files'] != baseline['files'] or current['others'] != baseline['others']:
                    raise UpdateError('PRESERVATION_FAILED')
                okay = current['image_id'] == image_id and current['restarts'] == 0 and self.healthy()
                stable = stable + 1 if okay else 0
                if stable >= 3:
                    return current
            except UpdateError as exc:
                if exc.code in {'PRESERVATION_FAILED', 'MOUNT_MISMATCH', 'COMPOSE_MISMATCH'}:
                    raise
                stable = 0
            self.sleep(2)
        raise UpdateError('HEALTH_CHECK_FAILED')

    def removable(self, image_id, protected):
        if image_id in protected or any(c['image'] == image_id for c in self.containers()):
            return False
        image = self.inspect_image(image_id)
        tags, refs = image.get('RepoTags') or [], image.get('RepoDigests') or []
        import re
        return bool(refs) and all(r.startswith(IMAGE + '@sha256:') for r in refs) and all(re.fullmatch(re.escape(IMAGE) + r':(?:[a-f0-9]{7,40}|latest)', t) for t in tags)

    def remove(self, image_id, protected):
        if not self.removable(image_id, protected):
            raise UpdateError('IMAGE_PROTECTED')
        self.command(['image', 'rm', image_id])  # no force, prune or volume command


class Engine:
    def __init__(self, driver, verifier, directory, spawn=None, *, recover=True):
        self.driver, self.verifier = driver, verifier
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'state.json'
        self.mutex = threading.RLock()
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=False).start())
        try:
            self.state = json.loads(self.path.read_text()) if self.path.exists() else {'version': 1, 'jobs': [], 'managed': [], 'rollback': None, 'nonces': {}}
            if self.state['version'] != 1:
                raise ValueError()
        except (ValueError, KeyError, OSError):
            raise UpdateError('STATE_CORRUPT') from None
        if recover:
            self.recover()

    def save(self):
        atomic(self.path, canonical(self.state))

    def stage(self, job, name, **extra):
        with self.mutex:
            job.update(stage=name, updated_at=int(time.time()), **extra)
            self.save()

    def recover(self):
        for job in self.state['jobs']:
            if job['stage'] in ACTIVE:
                if job.get('may_have_replaced'):
                    self.rollback(job)
                else:
                    self.stage(job, 'interrupted', error='WORKER_RESTARTED_BEFORE_REPLACEMENT')

    def rollback(self, job):
        self.stage(job, 'rolling_back')
        try:
            baseline = job['baseline']
            self.driver.inspect_image(baseline['image_id'])
            self.driver.replace(baseline['image_id'], baseline)
            restored = self.driver.verify(baseline['image_id'], baseline)
            if restored['digest'] != baseline['digest']:
                raise UpdateError('ROLLBACK_DIGEST_MISMATCH')
            self.stage(job, 'rolled_back', rollback_result='verified')
        except Exception:
            self.stage(job, 'rollback_failed', rollback_result='operator_required')

    @staticmethod
    def public_job(job):
        # Never expose filesystem baseline, credentials, Docker env or log text.
        return {k: job[k] for k in ('id', 'kind', 'stage', 'created_at', 'updated_at', 'error', 'sha', 'digest', 'confirmed', 'rollback_result', 'removed', 'skipped') if k in job}

    def status(self):
        with self.mutex:
            current = self.driver.snapshot()
            return {'current': {k: current[k] for k in ('sha', 'digest', 'image_id', 'restarts')},
                    'rollback': self.state['rollback'], 'jobs': [self.public_job(j) for j in self.state['jobs'][-20:]],
                    'busy': any(j['stage'] in ACTIVE for j in self.state['jobs'])}

    def protected(self):
        current = self.driver.snapshot()['image_id']
        rollback = (self.state['rollback'] or {}).get('image_id')
        return {current, rollback}

    def preview(self):
        installs = [j for j in self.state['jobs'] if j['kind'] == 'install' and j['stage'] == 'succeeded']
        if not installs or not installs[-1].get('confirmed'):
            raise UpdateError('USER_CONFIRMATION_REQUIRED')
        protected = self.protected()
        images = []
        for image_id in dict.fromkeys(self.state['managed']):
            try:
                if self.driver.removable(image_id, protected):
                    images.append(image_id)
            except UpdateError:
                continue  # absent/ambiguous images are never guessed or forced
        return {'images': images[:20], 'preserved': sorted(i for i in protected if i)}

    def dispatch(self, request):
        validate_request(request)
        method, args = request['method'], request['args']
        with self.mutex:
            nonce = request['nonce']
            if nonce in self.state['nonces']:
                raise UpdateError('IPC_REPLAY')
            now = int(time.time())
            self.state['nonces'] = {n: t for n, t in self.state['nonces'].items() if now - t <= 120}
            self.state['nonces'][nonce] = now
            self.save()
            if method == 'status':
                return self.status()
            if method == 'check':
                current = self.driver.snapshot()
                release = self.verifier.latest(current['sha'])
                return {**release, 'available': (release['sha'], release['digest']) != (current['sha'], current['digest']),
                        'free_bytes': self.driver.free_bytes(), 'required_bytes': max(2_147_483_648, release['compressed_bytes'] * 3 + 524_288_000)}
            if any(j['stage'] in ACTIVE or j['stage'] == 'rollback_failed' for j in self.state['jobs']):
                raise UpdateError('UPDATE_LOCKED')
            if method == 'confirm':
                job = next((j for j in self.state['jobs'] if j['id'] == args['job_id'] and j['kind'] == 'install'), None)
                if not job or job['stage'] != 'succeeded' or self.driver.snapshot()['digest'] != job['digest']:
                    raise UpdateError('JOB_NOT_CURRENT_SUCCESS')
                self.driver.verify(job['image_id'], job['baseline'])
                self.stage(job, 'succeeded', confirmed=True)
                return self.public_job(job)
            if method == 'cleanup_preview':
                return self.preview()
            if method == 'cleanup' and sorted(args['images']) != sorted(self.preview()['images']):
                raise UpdateError('CLEANUP_PLAN_CHANGED')
            job = {'id': nonce, 'kind': method, 'stage': 'queued', 'actor': request['actor'],
                   'created_at': now, 'updated_at': now, 'confirmed': False, **args}
            self.state['jobs'].append(job)
            self.save()
            self.spawn(lambda: self.run(job))
            return self.public_job(job)

    def run(self, job):
        try:
            if job['kind'] == 'cleanup':
                self.stage(job, 'cleaning')
                removed, skipped = [], []
                for image_id in job['images']:
                    try:
                        self.driver.remove(image_id, self.protected())
                        removed.append(image_id)
                    except UpdateError:
                        skipped.append(image_id)
                    self.stage(job, 'cleaning', removed=removed, skipped=skipped)
                self.stage(job, 'failed' if skipped else 'succeeded', **({'error': 'IMAGE_CLEANUP_PARTIAL'} if skipped else {}))
                return
            self.stage(job, 'checking')
            baseline = self.driver.snapshot()
            if not self.driver.healthy():
                raise UpdateError('CURRENT_HEALTH_FAILED')
            release = self.verifier.latest(baseline['sha'])
            if (release['sha'], release['digest']) != (job['sha'], job['digest']):
                raise UpdateError('RELEASE_CHANGED_RECHECK')
            if (baseline['sha'], baseline['digest']) == (job['sha'], job['digest']):
                raise UpdateError('ALREADY_CURRENT')
            required = max(2_147_483_648, release['compressed_bytes'] * 3 + 524_288_000)
            if self.driver.free_bytes() < required:
                raise UpdateError('INSUFFICIENT_SPACE')
            self.driver.inspect_image(baseline['image_id'])
            self.stage(job, 'pulling', baseline=baseline)
            image_id = self.driver.pull(job['digest'])
            image = self.driver.inspect_image(image_id)
            if (image.get('Config', {}).get('Labels') or {}).get('org.opencontainers.image.revision') != job['sha']:
                raise UpdateError('PULLED_REVISION_MISMATCH')
            # Ensure the operating configuration did not change while pulling.
            if self.driver.snapshot() != baseline:
                raise UpdateError('PREFLIGHT_CHANGED')
            self.stage(job, 'replacing', image_id=image_id, may_have_replaced=True)
            self.driver.replace(IMAGE + '@' + job['digest'], baseline)
            self.stage(job, 'verifying')
            current = self.driver.verify(image_id, baseline)
            if current['digest'] != job['digest'] or current['sha'] != job['sha']:
                raise UpdateError('RUNNING_IMAGE_MISMATCH')
            with self.mutex:
                self.state['rollback'] = {k: baseline[k] for k in ('sha', 'digest', 'image_id')}
                self.state['managed'] = list(dict.fromkeys([*self.state['managed'], baseline['image_id'], image_id]))
                self.stage(job, 'succeeded')
        except Exception as exc:
            self.stage(job, job['stage'], error=exc.code if isinstance(exc, UpdateError) else 'UPDATE_INTERNAL_ERROR')
            if job.get('may_have_replaced'):
                self.rollback(job)
            else:
                self.stage(job, 'failed')


def make_server(engine, runtime, key):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(55)
            nonce = None
            try:
                payload = validate_request(unseal(receive(self.request), key))
                nonce = payload['nonce']
                result = engine.dispatch(payload)
                reply = {'ok': True, 'result': result, 'nonce': nonce}
            except Exception as exc:
                reply = {'ok': False, 'error': exc.code if isinstance(exc, UpdateError) else 'WORKER_ERROR', 'nonce': nonce}
            self.request.sendall(canonical(seal(reply, key)) + b'\n')
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        request_queue_size = 8
        slots = threading.BoundedSemaphore(8)

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()
    path = Path(runtime) / 'worker.sock'
    if path.exists():
        if not path.is_socket():
            raise UpdateError('SOCKET_PATH_UNSAFE')
        path.unlink()
    server = Server(str(path), Handler)
    path.chmod(0o600)
    return server


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fixed-scope Wealth host worker')
    parser.add_argument('--recover-failed', action='store_true', help='operator only: retry recorded rollback while service is stopped')
    options = parser.parse_args()
    # Production paths cannot be selected by app/API input.
    directory = Path('/var/lib/wealth-updater')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with exclusive(directory / 'worker.lock'):
        key = Path('/etc/wealth-updater/client.key').read_bytes()
        if len(key) != 32:
            raise UpdateError('IPC_KEY_INVALID')
        runtime = Path('/run/wealth-updater')
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic(runtime / 'client.key', key)
        token_path = Path('/etc/wealth-updater/github.token')
        token = token_path.read_text().strip() if token_path.exists() else ''
        engine = Engine(DockerHost(), ReleaseVerifier(token), directory)
        if options.recover_failed:
            for job in engine.state['jobs']:
                if job['stage'] == 'rollback_failed':
                    engine.rollback(job)
            if any(j['stage'] == 'rollback_failed' for j in engine.state['jobs']):
                raise UpdateError('ROLLBACK_OPERATOR_REQUIRED')
            print('RECOVERY_VERIFIED')
            return
        with make_server(engine, runtime, key) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
