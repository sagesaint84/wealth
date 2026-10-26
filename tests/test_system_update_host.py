import copy
import json
import socket
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.updater.host import Engine, DockerHost, atomic, exclusive, make_server
from app.updater.protocol import IMAGE, HostClient, UpdateError, canonical, seal, unseal, validate_request

OLD_SHA, NEW_SHA = 'a'*40, 'b'*40
OLD_DIGEST, NEW_DIGEST = 'sha256:'+'a'*64, 'sha256:'+'b'*64
OLD_ID, NEW_ID = 'sha256:'+'c'*64, 'sha256:'+'d'*64


def request(method='install',args=None,nonce=None):
    return {'method':method,'args':({'sha':NEW_SHA,'digest':NEW_DIGEST} if method=='install' and args is None else args or {}),
            'actor':'synthetic-admin','nonce':nonce or uuid.uuid4().hex,'timestamp':int(time.time())}


class FakeDriver:
    def __init__(self):
        self.current=OLD_ID
        self.calls=[]
        self.fail=None
        self.rollback_fail=False
        self.free=10**12
        self.extra=[]
        self.removed=[]
        self.base={'project':'synthetic','mounts':[{'synthetic':'data/Toss sentinel'}], 'files':{'compose':'unchanged'},'others':[{'id':'unrelated','image':'other-image'}],'restarts':0}

    def snapshot(self):
        return {**copy.deepcopy(self.base),'image_id':self.current,'sha':NEW_SHA if self.current==NEW_ID else OLD_SHA,'digest':NEW_DIGEST if self.current==NEW_ID else OLD_DIGEST}

    def healthy(self):return True
    def free_bytes(self):return self.free
    def inspect_image(self,ref):
        return {'Id':ref,'Config':{'Labels':{'org.opencontainers.image.revision':NEW_SHA if ref==NEW_ID else OLD_SHA}}}
    def pull(self,digest):
        self.calls.append(('pull',digest))
        if self.fail=='pull':raise UpdateError('PULL_FAILED')
        return NEW_ID
    def replace(self,ref,baseline):
        self.calls.append(('replace',ref))
        if ref==OLD_ID and self.rollback_fail:raise UpdateError('ROLLBACK_FAILED')
        self.current=OLD_ID if ref==OLD_ID else NEW_ID
        if self.fail=='replace' and ref!=OLD_ID:raise UpdateError('REPLACE_TIMEOUT')
    def verify(self,image_id,baseline):
        self.calls.append(('verify',image_id))
        if self.fail=='verify' and image_id==NEW_ID:raise UpdateError('HEALTH_CHECK_FAILED')
        assert self.base['mounts']==baseline['mounts'] and self.base['others']==baseline['others'] and self.base['files']==baseline['files']
        return self.snapshot()
    def removable(self,image_id,protected):return image_id not in protected and image_id not in self.extra
    def remove(self,image_id,protected):
        assert self.removable(image_id,protected)
        self.removed.append(image_id)


@pytest.fixture
def worker(tmp_path):
    driver=FakeDriver();pending=[]
    release={'sha':NEW_SHA,'digest':NEW_DIGEST,'compressed_bytes':100,'changes':[]}
    verifier=Mock();verifier.latest.return_value=release
    engine=Engine(driver,verifier,tmp_path,spawn=pending.append)
    return engine,driver,verifier,pending


def finish(worker):
    engine,driver,verifier,pending=worker
    result=engine.dispatch(request())
    pending.pop(0)()
    return engine.state['jobs'][-1]


def test_success_pins_digest_preserves_baseline_and_requires_user_confirmation(worker):
    engine,driver,verifier,_=worker
    job=finish(worker)
    assert job['stage']=='succeeded' and not job['confirmed']
    assert driver.calls[:2]==[('pull',NEW_DIGEST),('replace',IMAGE+'@'+NEW_DIGEST)]
    assert engine.state['rollback']['image_id']==OLD_ID
    assert set(engine.state['managed'])=={OLD_ID,NEW_ID}
    assert 'baseline' not in engine.status()['jobs'][0]
    with pytest.raises(UpdateError,match='USER_CONFIRMATION_REQUIRED'):engine.dispatch(request('cleanup_preview'))
    engine.dispatch(request('confirm',{'job_id':job['id']}))
    assert job['confirmed']
    assert engine.preview()['preserved']==sorted([OLD_ID,NEW_ID])


@pytest.mark.parametrize('failure',['pull','replace','verify'])
def test_failure_and_timeout_roll_back_only_after_potential_replacement(worker,failure):
    engine,driver,_,_=worker;driver.fail=failure
    job=finish(worker)
    assert driver.current==OLD_ID
    if failure=='pull':
        assert job['stage']=='failed' and not any(c[0]=='replace' for c in driver.calls)
    else:
        assert job['stage']=='rolled_back' and job['rollback_result']=='verified'
        assert ('replace',OLD_ID) in driver.calls
    assert engine.state['rollback'] is None


def test_failed_rollback_blocks_following_update(worker):
    engine,driver,_,_=worker;driver.fail='verify';driver.rollback_fail=True
    assert finish(worker)['stage']=='rollback_failed'
    with pytest.raises(UpdateError,match='UPDATE_LOCKED'):engine.dispatch(request())


@pytest.mark.parametrize('failure',['space','release_changed','unavailable','current_health'])
def test_preflight_failures_leave_operating_image_untouched(worker,failure):
    engine,driver,verifier,_=worker
    if failure=='space':driver.free=100
    if failure=='release_changed':verifier.latest.return_value['sha']='e'*40
    if failure=='unavailable':verifier.latest.side_effect=UpdateError('RELEASE_UNAVAILABLE')
    if failure=='current_health':driver.healthy=lambda:False
    assert finish(worker)['stage']=='failed'
    assert driver.calls==[] and driver.current==OLD_ID


def test_duplicate_lock_and_replay_do_not_spawn_twice(worker):
    engine,driver,_,pending=worker
    req=request();engine.dispatch(req)
    with pytest.raises(UpdateError,match='IPC_REPLAY'):engine.dispatch(req)
    with pytest.raises(UpdateError,match='UPDATE_LOCKED'):engine.dispatch(request())
    assert len(pending)==1
    pending.pop()();assert driver.current==NEW_ID


@pytest.mark.parametrize('stage',['queued','pulling','replacing','verifying','rolling_back'])
def test_restart_recovers_durable_job_before_serving_requests(worker,tmp_path,stage):
    engine,driver,verifier,_=worker
    req=request();engine.dispatch(req)
    job=engine.state['jobs'][-1]
    baseline=driver.snapshot()
    changed=stage in {'replacing','verifying','rolling_back'}
    job.update(stage=stage,baseline=baseline,may_have_replaced=changed)
    if changed:driver.current=NEW_ID
    engine.save()
    restored=Engine(driver,verifier,tmp_path,spawn=lambda fn:None)
    job=restored.state['jobs'][-1]
    assert driver.current==OLD_ID
    assert job['stage']==('rolled_back' if changed else 'interrupted')
    assert restored.status()['busy'] is False


def test_corrupt_state_fails_closed_without_overwriting(tmp_path):
    path=tmp_path/'state.json';path.write_text('{bad')
    with pytest.raises(UpdateError,match='STATE_CORRUPT'):Engine(FakeDriver(),Mock(),tmp_path)
    assert path.read_text()=='{bad'


def test_cleanup_only_owned_recorded_unused_images_keep_current_and_rollback(worker):
    engine,driver,_,pending=worker
    job=finish(worker);engine.dispatch(request('confirm',{'job_id':job['id']}))
    candidate='sha256:'+'e'*64;other_in_use='sha256:'+'f'*64
    engine.state['managed'] += [candidate,other_in_use]
    driver.extra=[other_in_use]
    preview=engine.dispatch(request('cleanup_preview'))
    assert preview['images']==[candidate]
    with pytest.raises(UpdateError,match='CLEANUP_PLAN_CHANGED'):engine.dispatch(request('cleanup',{'images':[candidate,OLD_ID]}))
    engine.dispatch(request('cleanup',{'images':preview['images']}));pending.pop()()
    assert driver.removed==[candidate] and OLD_ID not in driver.removed and NEW_ID not in driver.removed


def test_cleanup_rechecks_new_container_reference_at_deletion(worker):
    engine,driver,_,pending=worker
    job=finish(worker);engine.dispatch(request('confirm',{'job_id':job['id']}))
    candidate='sha256:'+'e'*64;engine.state['managed'].append(candidate)
    engine.dispatch(request('cleanup',{'images':[candidate]}))
    # Fake daemon rejects a concurrently acquired reference, like Docker image rm.
    driver.remove=lambda image_id,protected:(_ for _ in ()).throw(UpdateError('IMAGE_PROTECTED'))
    pending.pop()()
    assert driver.removed==[] and engine.state['jobs'][-1]['skipped']==[candidate]


@pytest.mark.parametrize('patch', [{'method':'shell'},{'method':[]},{'args':{'sha':NEW_SHA,'digest':'latest'}},{'args':{'sha':NEW_SHA,'digest':NEW_DIGEST,'command':'docker system prune'}},{'timestamp':0},{'actor':'../root'},{'nonce':'bad'}])
def test_protocol_limits_commands_arguments_and_expiration(patch):
    value=request();value.update(patch)
    with pytest.raises(UpdateError):validate_request(value)


def test_hmac_tamper_rejection_and_process_lock(tmp_path):
    key=b'x'*32;signed=seal(request(),key)
    assert unseal(signed,key)==signed['payload']
    signed['payload']['args']['sha']='e'*40
    with pytest.raises(UpdateError,match='IPC_AUTH_FAILED'):unseal(signed,key)
    with exclusive(tmp_path/'lock'):
        with pytest.raises(UpdateError,match='WORKER_ALREADY_RUNNING'):
            with exclusive(tmp_path/'lock'):pass


@pytest.mark.skipif(not hasattr(socketserver := __import__('socketserver'), 'UnixStreamServer'),reason='Linux Unix IPC integration runs in required CI')
def test_real_authenticated_unix_ipc_roundtrip_and_bad_key(worker,tmp_path,monkeypatch):
    engine,_,_,_=worker;key=b'x'*32
    (tmp_path/'client.key').write_bytes(key)
    with make_server(engine,tmp_path,key) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        guarded=socket.socket.connect
        # Both tests/__init__.py and conftest.py wrap Python socket.connect.
        # Use the C base method ONLY for this one fixture-owned Unix path.
        native=__import__('_socket').socket.connect
        def connect(sock,address):
            if sock.family==socket.AF_UNIX and address==str(tmp_path/'worker.sock'):return native(sock,address)
            return guarded(sock,address)
        monkeypatch.setattr(socket.socket,'connect',connect)
        try:
            assert HostClient(tmp_path).call('status')['current']['image_id']==OLD_ID
            assert 'guard' in guarded.__name__
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as outside:
                with pytest.raises(AssertionError,match='External network is blocked'):
                    outside.connect(('192.0.2.1',443))
            (tmp_path/'client.key').write_bytes(b'y'*32)
            with pytest.raises(UpdateError,match='IPC_AUTH_FAILED'):HostClient(tmp_path).call('status')
        finally:
            server.shutdown();thread.join(3)


def test_docker_commands_fixed_argv_no_shell_and_timeout(tmp_path,monkeypatch):
    run=Mock(return_value=Mock(stdout=b'{}'))
    monkeypatch.setattr('app.updater.host.subprocess.run',run)
    driver=DockerHost(root=tmp_path,state=tmp_path)
    driver.command(['inspect','wealth'],timeout=9)
    args,kw=run.call_args
    assert args[0]==['/usr/bin/docker','inspect','wealth'] and kw['timeout']==9 and 'shell' not in kw
    assert kw['env']['DOCKER_CONFIG']=='/etc/wealth-updater/docker'
    with pytest.raises(UpdateError):driver.replace('latest',{'project':'synthetic'})
    run.assert_called_once()


@pytest.mark.parametrize('change',['other_repo','used','rollback','current','ambiguous_tag'])
def test_real_driver_cleanup_guards(tmp_path,change):
    driver=DockerHost(tmp_path,tmp_path)
    image={'RepoDigests':[IMAGE+'@'+NEW_DIGEST],'RepoTags':[IMAGE+':bbbbbbb']}
    if change=='other_repo':image['RepoDigests'].append('other/thing@'+OLD_DIGEST)
    if change=='ambiguous_tag':image['RepoTags'].append(IMAGE+':protected-manual')
    driver.inspect_image=lambda _:image
    driver.containers=lambda:[{'image':NEW_ID}] if change=='used' else []
    protected={NEW_ID} if change in {'rollback','current'} else set()
    driver.command=Mock()
    with pytest.raises(UpdateError,match='IMAGE_PROTECTED'):driver.remove(NEW_ID,protected)
    driver.command.assert_not_called()
