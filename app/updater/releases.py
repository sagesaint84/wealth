"""Host-only public release verification. Credentials never enter app IPC."""
from __future__ import annotations

import hashlib
import json
import re
import time
import threading
import urllib.parse
import urllib.request

from .protocol import REPO, IMAGE, SHA, DIGEST, UpdateError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReleaseVerifier:
    def __init__(self, token='', fetch=None):
        self.token = token
        self.fetch = fetch or self._fetch
        self.deadline = 0
        self.lock = threading.Lock()

    def _fetch(self, url, headers=None, limit=4_000_000):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise UpdateError('RELEASE_TIMEOUT')
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=min(8, remaining)) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise UpdateError('RELEASE_TOO_LARGE')
                return raw, dict(response.headers), response.status
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                return b'', dict(exc.headers), exc.code
            raise UpdateError('RELEASE_UNAVAILABLE') from None
        except (OSError, ValueError):
            raise UpdateError('RELEASE_UNAVAILABLE') from None

    def api(self, suffix):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Wealth-updater/2.1.4', 'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        raw, _, status = self.fetch(f'https://api.github.com/repos/{REPO}/{suffix}', headers)
        if status != 200:
            raise UpdateError('RELEASE_UNAVAILABLE')
        return json.loads(raw)

    def latest(self, current_sha=None):
        if not self.lock.acquire(blocking=False):
            raise UpdateError('RELEASE_CHECK_BUSY')
        try:
            return self._latest(current_sha)
        finally:
            self.lock.release()

    def _latest(self, current_sha=None):
        self.deadline = time.monotonic() + 45
        try:
            sha = self.api('branches/main')['commit']['sha']
            if not SHA.fullmatch(sha):
                raise UpdateError('RELEASE_INVALID')
            runs = self.api('actions/workflows/docker-publish.yml/runs?event=push&branch=main&head_sha=' + sha + '&per_page=10')['workflow_runs']
            runs = [r for r in runs if r['head_sha'] == sha and r['head_branch'] == 'main' and r['event'] == 'push' and r['path'] == '.github/workflows/docker-publish.yml' and r['repository']['full_name'] == REPO]
            if not runs:
                raise UpdateError('BUILD_NOT_READY')
            run = max(runs, key=lambda r: (r['run_number'], r.get('run_attempt', 1)))
            if run['status'] != 'completed' or run['conclusion'] != 'success':
                raise UpdateError('BUILD_NOT_SUCCESSFUL')
            jobs = self.api(f"actions/runs/{int(run['id'])}/jobs")['jobs']
            build = [j for j in jobs if j['name'] == 'build-and-push' and j['conclusion'] == 'success']
            if len(build) != 1:
                raise UpdateError('BUILD_NOT_SUCCESSFUL')
            # Retrieve the exact successful job's logs, never a mutable latest tag.
            headers = {'User-Agent': 'Wealth-updater/2.1.4'}
            if self.token:
                headers['Authorization'] = 'Bearer ' + self.token
            raw, redirect, status = self.fetch(f"https://api.github.com/repos/{REPO}/actions/jobs/{int(build[0]['id'])}/logs", headers)
            if status in (301, 302, 303, 307, 308):
                location = next((v for k, v in redirect.items() if k.lower() == 'location'), '')
                parts = urllib.parse.urlsplit(location)
                if parts.scheme != 'https' or parts.username or parts.password or not parts.hostname or not parts.hostname.endswith(('.blob.core.windows.net', '.actions.githubusercontent.com')):
                    raise UpdateError('LOG_REDIRECT_UNTRUSTED')
                raw, _, status = self.fetch(location, {})  # no GitHub bearer on redirect
            if status != 200:
                raise UpdateError('BUILD_EVIDENCE_UNAVAILABLE')
            matches = set(re.findall(r'pushing manifest for ' + re.escape(IMAGE) + ':' + re.escape(sha[:7]) + r'@(sha256:[a-f0-9]{64})', raw.decode('utf-8')))
            if len(matches) != 1:
                raise UpdateError('BUILD_DIGEST_UNCONFIRMED')
            digest = matches.pop()
            token_query = urllib.parse.urlencode({'service': 'ghcr.io', 'scope': f'repository:{REPO}:pull'})
            raw, _, status = self.fetch('https://ghcr.io/token?' + token_query)
            if status != 200:
                raise UpdateError('REGISTRY_UNAVAILABLE')
            token = json.loads(raw)['token']
            registry_headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'}
            def registry(path, expected):
                content, _, code = self.fetch(f'https://ghcr.io/v2/{REPO}/{path}', registry_headers)
                if code != 200 or 'sha256:' + hashlib.sha256(content).hexdigest() != expected:
                    raise UpdateError('REGISTRY_DIGEST_MISMATCH')
                return json.loads(content)
            index = registry('manifests/' + digest, digest)
            platforms, size = set(), 0
            for entry in index['manifests']:
                platform = entry.get('platform', {})
                if platform.get('os') != 'linux' or platform.get('architecture') not in {'amd64', 'arm64'}:
                    continue
                arch = platform['architecture']
                if arch in platforms or not DIGEST.fullmatch(entry['digest']):
                    raise UpdateError('PLATFORM_INVALID')
                manifest = registry('manifests/' + entry['digest'], entry['digest'])
                if not DIGEST.fullmatch(manifest['config']['digest']):
                    raise UpdateError('REGISTRY_DIGEST_MISMATCH')
                config = registry('blobs/' + manifest['config']['digest'], manifest['config']['digest'])
                if config.get('architecture') != arch or config.get('os') != 'linux':
                    raise UpdateError('PLATFORM_INVALID')
                if config['config']['Labels']['org.opencontainers.image.revision'] != sha:
                    raise UpdateError('IMAGE_REVISION_MISMATCH')
                platforms.add(arch)
                sizes = [layer['size'] for layer in manifest['layers']]
                if not sizes or any(type(n) is not int or not 0 <= n <= 20_000_000_000 for n in sizes):
                    raise UpdateError('IMAGE_SIZE_INVALID')
                size = max(size, sum(sizes))
            if platforms != {'amd64', 'arm64'}:
                raise UpdateError('PLATFORMS_MISSING')
            commits = []
            if current_sha and SHA.fullmatch(current_sha) and current_sha != sha:
                compared = self.api(f'compare/{current_sha}...{sha}?per_page=20')
                if compared['status'] not in {'ahead', 'identical'}:
                    raise UpdateError('MAIN_NOT_DESCENDANT')
                commits = [{'sha': c['sha'], 'message': c['commit']['message'][:500]} for c in compared.get('commits', [])[:20]]
            return {'sha': sha, 'digest': digest, 'build': 'success', 'run_id': run['id'],
                    'url': f"https://github.com/{REPO}/actions/runs/{run['id']}",
                    'compressed_bytes': size, 'changes': commits, 'checked_at': int(time.time())}
        except UpdateError:
            raise
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise UpdateError('RELEASE_INVALID') from None
