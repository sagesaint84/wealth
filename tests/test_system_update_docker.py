"""Actual Docker/Compose on a disposable GitHub runner ONLY, synthetic images.

Registry trust is tested separately against immutable synthetic HTTP documents.
Here inspect attaches fixture RepoDigests (local builds do not have registry
digests), while replacement/HTTP/gzip/mounts/rollback use the real Docker daemon.
Never enable this against Oracle or a developer's existing Docker services.
"""
import hashlib
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.updater.host import DockerHost, Engine
from app.updater.protocol import IMAGE
from tests.test_system_update_host import request, OLD_SHA, NEW_SHA, OLD_DIGEST, NEW_DIGEST

pytestmark=pytest.mark.skipif(os.getenv('WEALTH_UPDATER_DOCKER_TEST')!='1',reason='Disposable Linux Docker CI only')


@pytest.mark.parametrize('broken',[False,True])
def test_isolated_real_compose_swap_preservation_and_rollback(tmp_path,broken):
    assert os.getenv('GITHUB_ACTIONS')=='true' and os.name=='posix'
    def docker(*args,check=True):
        return subprocess.run(['/usr/bin/docker',*args],check=check,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.strip()
    assert 'wealth' not in docker('ps','-a','--format','{{.Names}}').split()
    assert 'wealth-updater-sentinel' not in docker('ps','-a','--format','{{.Names}}').split()
    runtime=Path('/run/wealth-updater')
    runtime.mkdir(exist_ok=True)
    (runtime/'synthetic-sentinel').write_text('synthetic IPC mount, no real credentials')
    root=tmp_path/'wealth';root.mkdir();state=tmp_path/'state';state.mkdir()
    for name in ['data','toss-wts/bin','toss-wts/config']:(root/name).mkdir(parents=True,exist_ok=True)
    for name in ['data/synthetic.json','toss-wts/bin/tossctl','toss-wts/config/synthetic.json']:(root/name).write_text('SYNTHETIC ONLY')
    (root/'server.py').write_text('''from http.server import HTTPServer,BaseHTTPRequestHandler
import gzip,os
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/': self.send_response(307); self.send_header('Location','/login'); self.end_headers(); return
  self.send_response(200); self.send_header('Content-Encoding','identity' if os.getenv('BROKEN')=='1' else 'gzip'); self.end_headers(); self.wfile.write(gzip.compress(b'synthetic'))
HTTPServer(('0.0.0.0',4829),Handler).serve_forever()
''')
    (root/'Dockerfile').write_text('FROM python:3.12-alpine\nARG SHA\nARG BROKEN=0\nLABEL org.opencontainers.image.revision=$SHA\nENV BROKEN=$BROKEN\nCOPY server.py /app/server.py\nCMD ["python","/app/server.py"]\n')
    tags=[IMAGE+':'+OLD_SHA,IMAGE+':'+NEW_SHA]
    ids=[]
    try:
        for sha,tag,bad in [(OLD_SHA,tags[0],False),(NEW_SHA,tags[1],broken)]:
            # VM-local fixture tags only; abort rather than overwrite a preexisting image.
            assert not docker('image','ls','--quiet',tag)
            docker('build','--network=none','--build-arg','SHA='+sha,'--build-arg','BROKEN='+str(int(bad)),'-t',tag,str(root))
            ids.append(docker('image','inspect','-f','{{.Id}}',tag))
        (root/'docker-compose.ghcr.yml').write_text(f'''services:
  dashboard:
    image: {tags[0]}
    container_name: wealth
    ports: ["127.0.0.1:4829:4829"]
    volumes:
      - ./data:/app/data
      - ./toss-wts/bin/tossctl:/opt/toss-wts/tossctl:ro
      - ./toss-wts/config:/opt/toss-wts/config
''')
        (root/'docker-compose.override.yml').write_text('services:\n  dashboard:\n    restart: unless-stopped\n')
        (root/'docker-compose.updater.yml').write_text('services:\n  dashboard:\n    volumes:\n      - /run/wealth-updater:/run/wealth-updater:ro\n')
        base=['compose','--project-directory',str(root),'-p','wealth-updater-synthetic']
        for name in ['docker-compose.ghcr.yml','docker-compose.override.yml','docker-compose.updater.yml']:base+=['-f',str(root/name)]
        docker(*base,'up','-d','--no-build','--pull','never','dashboard')
        docker('run','-d','--name','wealth-updater-sentinel',tags[0],'python','-c','import time;time.sleep(300)')
        driver=DockerHost(root,state,sleep=lambda _:time.sleep(.2))
        actual_inspect=driver.inspect_image
        def fixture_inspect(ref):
            if ref==IMAGE+'@'+OLD_DIGEST:ref=ids[0]
            if ref==IMAGE+'@'+NEW_DIGEST:ref=ids[1]
            image=actual_inspect(ref)
            image['RepoDigests']=[IMAGE+'@'+(OLD_DIGEST if image['Id']==ids[0] else NEW_DIGEST)]
            return image
        driver.inspect_image=fixture_inspect
        driver.pull=lambda digest:ids[1]  # prebuilt local synthetic fixture, never GHCR
        real_replace=driver.replace
        driver.replace=lambda ref,baseline:real_replace(ids[1] if ref==IMAGE+'@'+NEW_DIGEST else ref,baseline)
        baseline=driver.snapshot();driver.verify(ids[0],baseline)
        protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        verifier=Mock();verifier.latest.return_value={'sha':NEW_SHA,'digest':NEW_DIGEST,'compressed_bytes':100}
        pending=[];engine=Engine(driver,verifier,state,spawn=pending.append)
        engine.dispatch(request());pending.pop()()
        job=engine.state['jobs'][-1]
        assert job['stage']==('rolled_back' if broken else 'succeeded')
        assert driver.snapshot()['image_id']==ids[0 if broken else 1]
        assert driver.snapshot()['mounts']==baseline['mounts']
        assert driver.snapshot()['others']==baseline['others']
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in protected.items())
        assert driver.healthy()
    finally:
        # Only the exact synthetic containers created above; no prune or volumes.
        docker('rm','-f','wealth','wealth-updater-sentinel',check=False)
        for image_id in ids:docker('image','rm',image_id,check=False)
