"""No live network. Bind successful main Actions logs to both platform digests."""
import hashlib
import io
import json
import urllib.error
import urllib.request

import pytest

from app.updater.protocol import IMAGE, REPO, UpdateError, canonical
from app.updater.releases import NoRedirect, ReleaseVerifier

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


@pytest.fixture
def blob_redirect(published):
    """Synthetic registry/CDN only; capture even forbidden destination requests."""
    verifier,data,calls=published
    original=verifier.fetch
    destinations={};cdn_calls=[]
    def fetch(url,headers=None,**kwargs):
        if url.startswith(f'https://ghcr.io/v2/{REPO}/blobs/'):
            calls.append((url,headers))
            digest=url.rsplit('/',1)[-1]
            location=data.get('blob_location',f'https://pkg-containers.githubusercontent.com/ghcr1/blobs/{digest}?synthetic-signature=a%2Fb')
            destinations[location]=digest
            return b'',{data.get('location_header','Location'):location},data.get('blob_status',307)
        if url in destinations:
            calls.append((url,headers));cdn_calls.append((url,headers))
            digest=destinations[url]
            return data.get('cdn_content',data['objects'][digest]),{'Location':data.get('next_location',url)},data.get('cdn_status',200)
        return original(url,headers,**kwargs)
    verifier.fetch=fetch
    return verifier,data,calls,cdn_calls


@pytest.mark.parametrize('header',['Location','location','lOcAtIoN'])
def test_config_blob_307_verifies_both_platforms_without_forwarding_credentials(blob_redirect,header):
    verifier,data,calls,cdn_calls=blob_redirect
    data['location_header']=header
    result=verifier.latest('a'*40)
    assert result['sha']==SHA and result['digest']==data['index']
    assert result['build']=='success' and result['changes'][0]['message']=='Synthetic change'
    assert len(cdn_calls)==2  # AMD64 and ARM64 configs, each followed once.
    assert all(headers=={} for _,headers in cdn_calls)
    assert all('synthetic-GitHub-read-token' not in url and 'synthetic-registry-token' not in url for url,_ in cdn_calls)
    blobs=[(url,headers) for url,headers in calls if url.startswith(f'https://ghcr.io/v2/{REPO}/blobs/')]
    assert len(blobs)==2
    assert all(headers['Authorization']=='Bearer synthetic-registry-token' for _,headers in blobs)
    assert all('synthetic-GitHub-read-token' not in str(headers) for url,headers in calls if not url.startswith('https://api.github.com/'))


def test_blob_redirect_explicit_https_default_port_is_allowed(blob_redirect):
    verifier,data,_,cdn_calls=blob_redirect
    data['blob_location']='https://pkg-containers.githubusercontent.com:443/ghcr1/blob?synthetic-signature=1'
    assert verifier.latest()['digest']==data['index']
    assert len(cdn_calls)==2 and all(headers=={} for _,headers in cdn_calls)


@pytest.mark.parametrize('location',[
    '',None,123,'/relative','//pkg-containers.githubusercontent.com/blob',
    'http://pkg-containers.githubusercontent.com/blob',
    'ftp://pkg-containers.githubusercontent.com/blob','file:///tmp/blob',
    'https://evil.invalid/blob',
    'https://pkg-containers.githubusercontent.com.evil.invalid/blob',
    'https://sub.pkg-containers.githubusercontent.com/blob',
    'https://pkg-containers.githubusercontent.com./blob',
    'https://pkg-containers.githubusercontent.com@evil.invalid/blob',
    'https://user:synthetic-password@pkg-containers.githubusercontent.com/blob',
    'https://pkg-containers.githubusercontent.com:80/blob',
    'https://pkg-containers.githubusercontent.com:444/blob',
    'https://pkg-containers.githubusercontent.com:invalid/blob',
    'https://127.0.0.1/blob','https://[::1]/blob','https://[broken/blob',
    'https://pkg-containers.githubusercontent.com',
    'https://pkg-containers.githubusercontent.com?blob=1',
    'https://pkg-containers.githubusercontent.com//evil.invalid/blob',
    'https://pkg-containers.githubusercontent.com/blob#fragment',
    'https://pkg-containers.githubusercontent.com/blob#',
    'https://pkg-containers.githubusercontent.com\\@evil.invalid/blob',
    ' https://pkg-containers.githubusercontent.com/blob',
    '\nhttps://pkg-containers.githubusercontent.com/blob',
    'https://pkg-containers.githubusercontent.com/bl\tob',
    'https://pkg-containers.githubusercontent.com/blob\r\nX-Injected: yes',
    'https://pkg-containers.githubusercontent.com/blob\x00',
    'https://pkg-containers.githubusercontent.com/blob\x7f',
    'https://pkg-containers.githubusercontent.com/blob?bad=%ZZ',
    'https://pkg-containers.githubusercontent.com/blob?bad=%',
    'https://pkg-containers.githubusercontent.com/blob?bad=%0D%0A',
    'https://pkg-containers.githubusercontent.com/blob%00',
    'https://pkg-containers.githubusercontent.com/blob%7f',
])
def test_untrusted_or_malformed_blob_redirect_never_fetches_destination(blob_redirect,location):
    verifier,data,_,cdn_calls=blob_redirect
    data['blob_location']=location
    with pytest.raises(UpdateError,match='^REGISTRY_BLOB_REDIRECT_UNTRUSTED$'):
        verifier.latest()
    assert cdn_calls==[]


@pytest.mark.parametrize('status',[301,302,303,308])
def test_only_blob_307_may_be_followed(blob_redirect,status):
    verifier,data,_,cdn_calls=blob_redirect;data['blob_status']=status
    with pytest.raises(UpdateError,match='^REGISTRY_DIGEST_MISMATCH$'):verifier.latest()
    assert cdn_calls==[]


@pytest.mark.parametrize('headers',[{}, {'Location':'https://pkg-containers.githubusercontent.com/a',
                                         'location':'https://pkg-containers.githubusercontent.com/b'}])
def test_missing_or_ambiguous_blob_location_is_rejected(published,headers):
    verifier,_,calls=published;original=verifier.fetch
    def fetch(url,request_headers=None,**kwargs):
        if url.startswith(f'https://ghcr.io/v2/{REPO}/blobs/'):
            calls.append((url,request_headers));return b'',headers,307
        return original(url,request_headers,**kwargs)
    verifier.fetch=fetch
    with pytest.raises(UpdateError,match='^REGISTRY_BLOB_REDIRECT_UNTRUSTED$'):verifier.latest()
    assert not any(url.startswith('https://pkg-containers.githubusercontent.com/') for url,_ in calls)


@pytest.mark.parametrize('status',[301,302,303,307,308,403,404,500])
def test_second_redirect_and_failed_cdn_response_are_not_followed(blob_redirect,status):
    verifier,data,calls,cdn_calls=blob_redirect
    data['cdn_status']=status;data['next_location']='https://evil.invalid/second-hop'
    with pytest.raises(UpdateError,match='^REGISTRY_DIGEST_MISMATCH$'):verifier.latest()
    assert len(cdn_calls)==1 and cdn_calls[0][1]=={}
    assert not any(url==data['next_location'] for url,_ in calls)


def test_second_redirect_to_same_trusted_cdn_is_also_rejected(blob_redirect):
    verifier,data,calls,cdn_calls=blob_redirect
    data['cdn_status']=307
    data['next_location']='https://pkg-containers.githubusercontent.com/second-hop'
    with pytest.raises(UpdateError,match='^REGISTRY_DIGEST_MISMATCH$'):verifier.latest()
    assert len(cdn_calls)==1
    assert not any(url==data['next_location'] for url,_ in calls)


@pytest.mark.parametrize('content',[b'',b'tampered-image-config',canonical({'architecture':'amd64','os':'linux'})])
def test_actual_cdn_bytes_must_match_original_config_digest(blob_redirect,content):
    verifier,data,_,cdn_calls=blob_redirect;data['cdn_content']=content
    with pytest.raises(UpdateError,match='^REGISTRY_DIGEST_MISMATCH$'):verifier.latest()
    assert len(cdn_calls)==1


def test_manifest_307_is_not_followed(published):
    verifier,data,calls=published;original=verifier.fetch
    destination='https://pkg-containers.githubusercontent.com/manifest'
    def fetch(url,headers=None,**kwargs):
        if '/manifests/' in url:
            calls.append((url,headers));return b'',{'Location':destination},307
        return original(url,headers,**kwargs)
    verifier.fetch=fetch
    with pytest.raises(UpdateError,match='^REGISTRY_DIGEST_MISMATCH$'):verifier.latest()
    assert not any(url==destination for url,_ in calls)


def test_github_api_307_is_still_rejected(published):
    verifier,_,calls=published
    def fetch(url,headers=None,**kwargs):
        calls.append((url,headers))
        return b'',{'Location':'https://pkg-containers.githubusercontent.com/api'},307
    verifier.fetch=fetch
    with pytest.raises(UpdateError,match='^RELEASE_UNAVAILABLE$'):verifier.latest()
    assert len(calls)==1


@pytest.mark.parametrize('failure',['architecture','os','revision','invalid_digest'])
@pytest.mark.parametrize('target',[0,1],ids=['amd64','arm64'])
def test_redirect_does_not_bypass_oci_platform_revision_or_digest_validation(blob_redirect,failure,target):
    verifier,data,_,cdn_calls=blob_redirect
    index=json.loads(data['objects'][data['index']])
    manifest=json.loads(data['objects'][index['manifests'][target]['digest']])
    config=json.loads(data['objects'][manifest['config']['digest']])
    def obj(value):
        raw=canonical(value);digest='sha256:'+hashlib.sha256(raw).hexdigest()
        data['objects'][digest]=raw;return digest
    if failure=='invalid_digest':
        manifest['config']['digest']='sha256:'+'g'*64
    else:
        if failure=='revision':config['config']['Labels']['org.opencontainers.image.revision']='a'*40
        else:config[failure]='windows' if failure=='os' else ('arm64' if target==0 else 'amd64')
        manifest['config']['digest']=obj(config)
    index['manifests'][target]['digest']=obj(manifest)
    data['log_digest']=obj(index)
    error={'revision':'IMAGE_REVISION_MISMATCH','invalid_digest':'REGISTRY_DIGEST_MISMATCH'}.get(failure,'PLATFORM_INVALID')
    with pytest.raises(UpdateError,match='^'+error+'$'):verifier.latest()
    assert len(cdn_calls)==target+(0 if failure=='invalid_digest' else 1)


def test_default_fetch_uses_no_redirect_opener_and_anonymous_cdn_requests(blob_redirect,monkeypatch):
    """Exercise real _fetch request creation with a wholly synthetic opener."""
    verifier,data,_,cdn_calls=blob_redirect
    synthetic=verifier.fetch;requests=[]
    class Response(io.BytesIO):
        def __init__(self,raw,headers,status):
            super().__init__(raw);self.headers=headers;self.status=status
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            assert 0<timeout<=8
            raw,headers,status=synthetic(request.full_url,dict(request.header_items()))
            if status!=200:
                raise urllib.error.HTTPError(request.full_url,status,'synthetic',headers,None)
            return Response(raw,headers,status)
    def build_opener(*handlers):
        assert len(handlers)==1 and isinstance(handlers[0],NoRedirect)
        return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',build_opener)
    verifier.fetch=verifier._fetch
    assert verifier.latest()['digest']==data['index']
    assert len(cdn_calls)==2
    for request in requests:
        if request.full_url.startswith('https://pkg-containers.githubusercontent.com/'):
            assert request.get_method()=='GET' and request.header_items()==[]


def test_no_redirect_handler_still_blocks_automatic_following():
    handler=NoRedirect()
    assert handler.redirect_request(None,None,307,'synthetic',{},'https://evil.invalid/') is None
