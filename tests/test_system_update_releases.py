"""No live network. Bind successful main Actions logs to both platform digests."""
import hashlib
import json

import pytest

from app.updater.protocol import IMAGE, REPO, UpdateError, canonical
from app.updater.releases import ReleaseVerifier

SHA='b'*40


@pytest.fixture
def published():
    objects={};calls=[]
    def obj(value):
        raw=canonical(value);digest='sha256:'+hashlib.sha256(raw).hexdigest();objects[digest]=raw;return digest
    manifests=[]
    for arch in ['amd64','arm64']:
        config=obj({'architecture':arch,'os':'linux','config':{'Labels':{'org.opencontainers.image.revision':SHA}}})
        manifest=obj({'config':{'digest':config},'layers':[{'size':100}]})
        manifests.append({'platform':{'os':'linux','architecture':arch},'digest':manifest})
    index=obj({'manifests':manifests})
    run={'id':100,'run_number':1,'run_attempt':1,'head_sha':SHA,'head_branch':'main','event':'push','path':'.github/workflows/docker-publish.yml','repository':{'full_name':REPO},'status':'completed','conclusion':'success'}
    job={'id':200,'name':'build-and-push','conclusion':'success'}
    data={'run':run,'job':job,'objects':objects,'index':index,'redirect':False,'log_digest':index,'manifest_sha':SHA,'platforms':manifests}
    def fetch(url,headers=None,**kwargs):
        calls.append((url,headers))
        if url.endswith('branches/main'):value={'commit':{'sha':SHA}}
        elif '/actions/workflows/' in url:value={'workflow_runs':[data['run']]}
        elif url.endswith('/jobs'):value={'jobs':[data['job']]}
        elif url.endswith('/logs'):
            if data['redirect']:return b'',{'Location':data['redirect']},302
            return f'pushing manifest for {IMAGE}:{SHA[:7]}@{data["log_digest"]}'.encode(),{},200
        elif '.blob.core.windows.net' in url:
            assert not headers.get('Authorization')
            return f'pushing manifest for {IMAGE}:{SHA[:7]}@{data["log_digest"]}'.encode(),{},200
        elif '/token?' in url:value={'token':'synthetic-registry-token'}
        elif '/manifests/' in url or '/blobs/' in url:
            digest=url.rsplit('/',1)[-1]
            return data['objects'].get(digest,b'wrong-bytes'),{},200
        elif '/compare/' in url:value={'status':'ahead','commits':[{'sha':SHA,'commit':{'message':'Synthetic change'}}]}
        else:raise AssertionError('Unexpected network path '+url)
        return canonical(value),{},200
    return ReleaseVerifier('synthetic-GitHub-read-token',fetch),data,calls


def test_successful_main_logs_index_architectures_revision_and_changes(published):
    verifier,data,calls=published
    result=verifier.latest('a'*40)
    assert result['sha']==SHA and result['digest']==data['index'] and result['build']=='success'
    assert result['changes'][0]['message']=='Synthetic change'
    assert all(':latest' not in url for url,_ in calls)
    assert all(not headers or 'synthetic-GitHub-read-token' not in str(headers) for url,headers in calls if 'api.github.com' not in url)


@pytest.mark.parametrize('field,value',[('head_branch','other'),('event','pull_request'),('path','.github/workflows/evil.yml'),('head_sha','a'*40),('status','in_progress'),('conclusion','failure'),('conclusion','cancelled'),('repository',{'full_name':'other/repo'})])
def test_wrong_or_unfinished_build_cannot_be_installed(published,field,value):
    verifier,data,calls=published;data['run'][field]=value
    with pytest.raises(UpdateError):verifier.latest()
    assert not any('/manifests/' in url for url,_ in calls)


@pytest.mark.parametrize('failure',['job_failed','digest_changed','platform_missing','config_revision','invalid_json'])
def test_registry_and_build_evidence_mismatch_fail_closed(published,failure):
    verifier,data,_=published
    if failure=='job_failed':data['job']['conclusion']='failure'
    if failure=='digest_changed':data['log_digest']='sha256:'+'f'*64
    if failure=='platform_missing':
        raw=canonical({'manifests':data['platforms'][:1]});digest='sha256:'+hashlib.sha256(raw).hexdigest()
        data['objects'][digest]=raw;data['log_digest']=digest
    if failure=='config_revision':
        # Digest bytes are checked before even trusting the false label.
        d=json.loads(data['objects'][data['platforms'][0]['digest']])['config']['digest']
        data['objects'][d]=canonical({'config':{'Labels':{'org.opencontainers.image.revision':'a'*40}}})
    if failure=='invalid_json':data['objects'][data['index']]=b'{bad'
    with pytest.raises(UpdateError):verifier.latest()


@pytest.mark.parametrize('redirect',['https://evil.invalid/log','http://example.blob.core.windows.net/log','https://token@x.blob.core.windows.net/log','https://127.0.0.1/log'])
def test_untrusted_log_redirect_does_not_receive_credentials(published,redirect):
    verifier,data,calls=published;data['redirect']=redirect
    with pytest.raises(UpdateError,match='LOG_REDIRECT_UNTRUSTED'):verifier.latest()
    assert not any(url==redirect for url,_ in calls)


def test_trusted_log_redirect_receives_no_GitHub_bearer(published):
    verifier,data,_=published;data['redirect']='https://results.blob.core.windows.net/log?synthetic-sas'
    assert verifier.latest()['digest']==data['index']
