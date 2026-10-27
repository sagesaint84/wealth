"""Offline synthetic state only. Never contact Docker/systemd/financial stores."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.updater import maintenance as m
from app.updater.host import ACTIVE, Engine, atomic, exclusive
from app.updater.protocol import UpdateError, canonical, validate_request
from tests.test_system_update_host import FakeDriver, OLD_SHA, NEW_SHA, OLD_DIGEST, NEW_DIGEST, OLD_ID, NEW_ID, request


@pytest.fixture
def offline(tmp_path):
    driver = FakeDriver()
    driver.current = NEW_ID
    driver.containers = Mock(return_value=[{'id': 'wealth-fixture', 'image': NEW_ID}, {'id': 'other', 'image': 'other-image'}])
    driver.image_absent = Mock(return_value=True)
    driver.replace = Mock(side_effect=AssertionError('No replacement allowed'))
    driver.pull = Mock(side_effect=AssertionError('No pull allowed'))
    driver.remove = Mock(side_effect=AssertionError('No deletion allowed'))
    expected = {'current': {'sha': NEW_SHA, 'digest': NEW_DIGEST, 'image_id': NEW_ID},
                'rollback': {'sha': OLD_SHA, 'digest': OLD_DIGEST, 'image_id': OLD_ID}, 'job_id': '1' * 32}
    baseline = {**driver.snapshot(), **expected['rollback']}
    state = {'version': 1, 'rollback': copy.deepcopy(expected['rollback']), 'managed': [OLD_ID, NEW_ID],
             'jobs': [{'id': expected['job_id'], 'kind': 'install', 'stage': 'succeeded', 'confirmed': True,
                       'may_have_replaced': True, 'baseline': baseline, **expected['current']}],
             'nonces': {'synthetic-nonce': 1}, 'future': {'preserve': True}}
    # Noncanonical original bytes prove that backup/failed-save restoration is exact.
    raw = json.dumps(state, indent=2).encode()
    atomic(tmp_path / 'state.json', raw)
    for name in ('pin.yml', 'client.key', 'compose-sentinel', 'finance-sentinel', 'toss-sentinel'):
        (tmp_path / name).write_bytes(b'synthetic-unchanged')
    engine = Engine(driver, None, tmp_path, recover=False)
    return engine, driver, expected, raw


def run(offline, **kwargs):
    engine, _, expected, _ = offline
    with exclusive(engine.directory / 'worker.lock'):
        return m.retire(engine, expected, stopped=lambda: None, **kwargs)


def test_dry_run_does_not_write_state_or_create_backup(offline):
    engine, driver, _, raw = offline
    assert run(offline) == {'action': 'dry-run', 'rollback_image_exists': False,
                           'automatic_rollback_available': False, 'changed': False}
    assert engine.path.read_bytes() == raw
    assert list(engine.directory.glob('rollback-retire-*.json')) == []
    driver.pull.assert_not_called(); driver.replace.assert_not_called(); driver.remove.assert_not_called()


def test_retirement_changes_only_rollback_with_durable_exact_backup(offline, monkeypatch):
    engine, driver, _, raw = offline
    original = copy.deepcopy(engine.state)
    save = Mock(wraps=engine.save); monkeypatch.setattr(engine, 'save', save)
    result = run(offline, apply=True)
    original['rollback'] = None
    assert engine.state == original and engine.path.read_bytes() == canonical(original)
    assert result['changed'] and not result['automatic_rollback_available']
    backups = list(engine.directory.glob('rollback-retire-*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == raw
    save.assert_called_once()
    for name in ('pin.yml', 'client.key', 'compose-sentinel', 'finance-sentinel', 'toss-sentinel'):
        assert (engine.directory / name).read_bytes() == b'synthetic-unchanged'
    driver.pull.assert_not_called(); driver.replace.assert_not_called(); driver.remove.assert_not_called()


@pytest.mark.parametrize('stage', sorted(ACTIVE | {'rollback_failed', 'unknown'}))
def test_active_failed_or_unknown_jobs_are_rejected_without_recovery(offline, stage):
    engine, driver, _, _ = offline
    engine.state['jobs'].append({'kind': 'install', 'stage': stage, 'may_have_replaced': True})
    engine.save(); before = engine.path.read_bytes()
    reloaded = Engine(driver, None, engine.directory, recover=False)
    assert reloaded.path.read_bytes() == before
    with pytest.raises(UpdateError, match='MAINTENANCE_JOB_LOCKED'): run(offline, apply=True)
    assert engine.path.read_bytes() == before
    driver.replace.assert_not_called()


@pytest.mark.parametrize('target', ['current', 'rollback'])
@pytest.mark.parametrize('key', ['sha', 'digest', 'image_id'])
def test_operator_expected_identity_must_match_exactly(offline, target, key):
    engine, _, expected, raw = offline
    expected[target][key] = 'e' * 40 if key == 'sha' else 'sha256:' + 'e' * 64
    with pytest.raises(UpdateError): run(offline, apply=True)
    assert engine.path.read_bytes() == raw


@pytest.mark.parametrize('failure', ['present', 'used', 'daemon', 'unconfirmed', 'failed_install', 'wrong_job',
                                     'baseline', 'managed', 'same_current', 'health', 'restart', 'state_race',
                                     'mounts', 'files', 'others'])
def test_ambiguous_or_unsafe_conditions_fail_closed(offline, failure):
    engine, driver, expected, _ = offline
    if failure == 'present': driver.image_absent.return_value = False
    if failure == 'used': driver.containers.return_value.append({'id': 'stopped-other', 'image': OLD_ID})
    if failure == 'daemon': driver.image_absent.side_effect = UpdateError('MAINTENANCE_IMAGE_UNCONFIRMED')
    if failure == 'unconfirmed': engine.state['jobs'][-1]['confirmed'] = False
    if failure == 'failed_install': engine.state['jobs'][-1]['stage'] = 'failed'
    if failure == 'wrong_job': expected['job_id'] = '2' * 32
    if failure == 'baseline': engine.state['jobs'][-1]['baseline']['image_id'] = NEW_ID
    if failure == 'managed': engine.state['managed'] = [NEW_ID]
    if failure == 'same_current': expected['rollback']['image_id'] = NEW_ID
    if failure == 'health': driver.healthy = lambda: False
    if failure == 'restart': driver.base['restarts'] = 1
    if failure in {'mounts', 'files', 'others'}: engine.state['jobs'][-1]['baseline'][failure] = None
    engine.save()
    if failure == 'state_race': engine.path.write_bytes(b'{"changed":true}')
    before = engine.path.read_bytes()
    with pytest.raises(UpdateError): run(offline, apply=True)
    assert engine.path.read_bytes() == before


@pytest.mark.parametrize('failure', ['backup', 'save_before_replace', 'save_after_replace', 'postflight', 'preflight'])
def test_failures_preserve_or_restore_original_bytes(offline, monkeypatch, failure):
    engine, driver, _, raw = offline
    if failure == 'backup': monkeypatch.setattr(m, 'atomic', Mock(side_effect=OSError('synthetic fsync failure')))
    if failure in {'save_before_replace', 'save_after_replace'}:
        def save():
            if failure == 'save_after_replace': atomic(engine.path, canonical(engine.state))
            raise OSError('synthetic save failure')
        monkeypatch.setattr(engine, 'save', save)
    if failure == 'postflight': driver.image_absent.side_effect = [True, True, False]
    if failure == 'preflight': driver.image_absent.side_effect = [True, False]
    with pytest.raises((UpdateError, OSError)): run(offline, apply=True)
    assert engine.path.read_bytes() == raw
    assert engine.state['rollback'] is not None


def test_restore_failure_leaves_valid_backup_and_requires_operator(offline, monkeypatch):
    engine, _, _, raw = offline
    real_atomic = m.atomic
    def fail_restore(path, value):
        if path == engine.path: raise OSError('synthetic restore failure')
        real_atomic(path, value)
    monkeypatch.setattr(m, 'atomic', fail_restore)
    monkeypatch.setattr(engine, 'save', Mock(side_effect=OSError('synthetic save failure')))
    with pytest.raises(UpdateError, match='MAINTENANCE_RESTORE_REQUIRED'): run(offline, apply=True)
    assert next(engine.directory.glob('rollback-retire-*.json')).read_bytes() == raw


@pytest.mark.parametrize('code,out,err,expected', [
    (1, b'[]\n', ('Error response from daemon: No such image: ' + OLD_ID + '\n').encode(), True),
    (0, b'[]', b'', False), (1, b'[]', b'Cannot connect to Docker daemon', None),
    (1, b'[]', b'permission denied', None), (1, b'', b'No such image', None),
])
def test_absence_requires_exact_daemon_evidence(tmp_path, monkeypatch, code, out, err, expected):
    command = Mock(return_value=Mock(returncode=code, stdout=out, stderr=err))
    monkeypatch.setattr(m.subprocess, 'run', command)
    driver = m.MaintenanceDockerHost(tmp_path, tmp_path)
    if expected is None:
        with pytest.raises(UpdateError, match='MAINTENANCE_IMAGE_UNCONFIRMED'): driver.image_absent(OLD_ID)
    else: assert driver.image_absent(OLD_ID) is expected
    assert command.call_args.args[0] == ['/usr/bin/docker', 'image', 'inspect', OLD_ID]
    assert command.call_args.kwargs['check'] is False and 'shell' not in command.call_args.kwargs


@pytest.mark.parametrize('code,output', [(0, b'active'), (3, b'failed'), (4, b'unknown')])
def test_service_must_be_stopped_not_failed_or_unknown(monkeypatch, code, output):
    monkeypatch.setattr(m.subprocess, 'run', Mock(return_value=Mock(returncode=code, stdout=output)))
    with pytest.raises(UpdateError): m.service_stopped()


def test_stopped_service_and_exclusive_lock(offline, monkeypatch):
    monkeypatch.setattr(m.subprocess, 'run', Mock(return_value=Mock(returncode=3, stdout=b'inactive\n')))
    m.service_stopped()
    with exclusive(offline[0].directory / 'worker.lock'):
        with pytest.raises(UpdateError, match='WORKER_ALREADY_RUNNING'): run(offline, apply=True)


def test_retirement_is_not_an_ipc_method():
    with pytest.raises(UpdateError): validate_request(request('retire_rollback'))


@pytest.mark.parametrize('fail', [False, True])
def test_future_update_and_automatic_rollback_still_work(offline, fail):
    engine, driver, _, _ = offline
    run(offline, apply=True)
    # A subsequent update still records the *current* baseline and can restore
    # it even though an older, missing long-term reference was retired.
    next_sha, next_digest, next_id = 'e' * 40, 'sha256:' + 'e' * 64, 'sha256:' + 'f' * 64
    baseline = driver.snapshot()
    class FutureDriver(FakeDriver):
        def __init__(self):
            super().__init__(); self.current = NEW_ID
        def snapshot(self):
            return {**copy.deepcopy(baseline), **({'sha': next_sha, 'digest': next_digest, 'image_id': next_id} if self.current == next_id else {})}
        def inspect_image(self, ref):
            return {'Id': ref, 'Config': {'Labels': {'org.opencontainers.image.revision': next_sha if ref == next_id else NEW_SHA}}}
        def pull(self, digest):
            assert digest == next_digest; return next_id
        def replace(self, ref, snapshot):
            self.calls.append(('replace', ref)); self.current = NEW_ID if ref == NEW_ID else next_id
        def verify(self, image_id, snapshot):
            if fail and image_id == next_id: raise UpdateError('HEALTH_CHECK_FAILED')
            return self.snapshot()
    verifier = Mock(); verifier.latest.return_value = {'sha': next_sha, 'digest': next_digest, 'compressed_bytes': 1}
    fresh_driver = FutureDriver()
    pending = []
    resumed = Engine(fresh_driver, verifier, engine.directory, spawn=pending.append)
    resumed.dispatch(request(args={'sha': next_sha, 'digest': next_digest})); pending.pop()()
    assert resumed.state['jobs'][-1]['stage'] == ('rolled_back' if fail else 'succeeded')
    if fail:
        assert ('replace', NEW_ID) in fresh_driver.calls and fresh_driver.current == NEW_ID
    else:
        assert resumed.state['rollback'] == {k: baseline[k] for k in ('sha', 'digest', 'image_id')}


def cli_args(expected):
    values = ['--expect-install-job', expected['job_id']]
    for key in ('current', 'rollback'):
        for field, value in expected[key].items(): values += ['--expect-' + key + '-' + field.replace('_', '-'), value]
    return values


@pytest.mark.parametrize('uid', [1000, 65534])
def test_cli_requires_host_root_before_accessing_state(offline, monkeypatch, uid):
    monkeypatch.setattr(m, 'os', SimpleNamespace(name='posix', geteuid=lambda: uid))
    stopped = Mock(); monkeypatch.setattr(m, 'service_stopped', stopped)
    with pytest.raises(UpdateError, match='MAINTENANCE_ROOT_REQUIRED'): m.main(cli_args(offline[2]))
    stopped.assert_not_called()


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('stage', [None, 'queued', 'rollback_failed'])
def test_cli_reuses_lock_without_automatic_recovery(offline, monkeypatch, capsys, apply, stage):
    engine, driver, expected, _ = offline
    monkeypatch.setattr(m, 'os', SimpleNamespace(name='posix', geteuid=lambda: 0))
    monkeypatch.setattr(m, 'DIRECTORY', engine.directory)
    monkeypatch.setattr(m, 'secure_path', Mock())
    monkeypatch.setattr(m, 'service_stopped', lambda: None)
    monkeypatch.setattr(m, 'MaintenanceDockerHost', lambda: driver)
    argv = cli_args(expected) + (['--apply', '--confirm-forget-missing-rollback'] if apply else [])
    if stage:
        engine.state['jobs'][-1]['stage'] = stage; engine.save()
        raw = engine.path.read_bytes()
        with pytest.raises(UpdateError, match='MAINTENANCE_JOB_LOCKED'): m.main(argv)
        assert engine.path.read_bytes() == raw
        driver.replace.assert_not_called()
        return
    m.main(argv)
    result = json.loads(capsys.readouterr().out)
    assert result['changed'] == apply


@pytest.mark.parametrize('flag', ['--apply', '--confirm-forget-missing-rollback'])
def test_cli_apply_requires_both_explicit_flags(offline, monkeypatch, flag):
    monkeypatch.setattr(m, 'os', SimpleNamespace(name='posix', geteuid=lambda: 0))
    with pytest.raises(UpdateError, match='MAINTENANCE_CONFIRMATION_REQUIRED'):
        m.main(cli_args(offline[2]) + [flag])


@pytest.mark.parametrize('mode,uid', [(0o100644, 0), (0o100600, 1000), (0o120777, 0), (0o040700, 0)])
def test_sensitive_state_path_rejects_shared_foreign_symlink_or_directory(mode, uid):
    path = Mock(); path.lstat.return_value = SimpleNamespace(st_mode=mode, st_uid=uid)
    with pytest.raises(UpdateError, match='MAINTENANCE_PATH_UNSAFE'): m.secure_path(path)
