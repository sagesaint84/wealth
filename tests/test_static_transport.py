"""HTTP representation contracts for synthetic/public static assets only."""
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient
from app.static_transport import CompressedStaticFiles


@pytest.fixture
def assets(tmp_path):
    for name in ('bundle.js','theme.css','small.js','image.png','data.json'):
        (tmp_path/name).write_bytes(b'const synthetic = 123;\n'*500 if name!='small.js' else b'/* small */')
    app=Starlette(routes=[Mount('/static',CompressedStaticFiles(directory=tmp_path)),
        Route('/api/example',lambda request: JSONResponse({'value':'synthetic'*2000}))])
    with TestClient(app) as client:
        yield client,tmp_path


@pytest.mark.parametrize('name',['bundle.js','theme.css'])
def test_gzip_decompresses_to_exact_original_and_preserves_mime(assets,name):
    client,root=assets
    plain=client.get('/static/'+name,headers={'Accept-Encoding':'identity'})
    packed=client.get('/static/'+name,headers={'Accept-Encoding':'gzip'})
    assert plain.status_code==packed.status_code==200
    assert plain.content==packed.content==(root/name).read_bytes()
    assert packed.headers['Content-Encoding']=='gzip'
    assert int(packed.headers['Content-Length'])<int(plain.headers['Content-Length'])/2
    assert packed.headers['Content-Type']==plain.headers['Content-Type']
    assert packed.headers['ETag']==plain.headers['ETag']
    assert packed.headers['Last-Modified']==plain.headers['Last-Modified']
    assert 'accept-encoding' in packed.headers['Vary'].lower()
    assert 'accept-encoding' in plain.headers['Vary'].lower()


@pytest.mark.parametrize('encoding',['identity','gzip;q=0','br, gzip;q=0','gzip;q=invalid'])
def test_encoding_refusal_keeps_original_bytes(assets,encoding):
    client,root=assets
    response=client.get('/static/bundle.js',headers={'Accept-Encoding':encoding})
    assert 'Content-Encoding' not in response.headers
    assert response.content==(root/'bundle.js').read_bytes()
    assert 'accept-encoding' in response.headers['Vary'].lower()


@pytest.mark.parametrize('path',['/static/image.png','/static/data.json','/static/small.js','/api/example'])
def test_no_compression_for_images_json_small_files_or_api(assets,path):
    client,_=assets
    response=client.get(path,headers={'Accept-Encoding':'gzip'})
    assert response.status_code==200
    assert 'Content-Encoding' not in response.headers


def test_range_head_conditional_and_missing_assets_preserve_semantics(assets):
    client,root=assets
    first=client.get('/static/bundle.js',headers={'Accept-Encoding':'gzip'})
    cached=client.get('/static/bundle.js',headers={'Accept-Encoding':'gzip','If-None-Match':first.headers['ETag']})
    assert cached.status_code==304 and cached.content==b''
    assert 'accept-encoding' in cached.headers['Vary'].lower()
    head=client.head('/static/bundle.js',headers={'Accept-Encoding':'gzip'})
    assert head.content==b'' and int(head.headers['Content-Length'])==(root/'bundle.js').stat().st_size
    assert 'Content-Encoding' not in head.headers
    ranged=client.get('/static/bundle.js',headers={'Accept-Encoding':'gzip','Range':'bytes=0-9'})
    assert ranged.status_code==206 and ranged.content==(root/'bundle.js').read_bytes()[:10]
    assert 'Content-Encoding' not in ranged.headers
    assert ranged.headers['Content-Range'].startswith('bytes 0-9/')
    assert client.get('/static/missing.js').status_code==404
    assert client.get('/static/%2e%2e/private.js').status_code==404


def test_main_uses_only_static_mount_not_global_api_compression():
    from tests.test_request_state_user_id import _import_main_without_loading_real_env
    app=_import_main_without_loading_real_env().app
    mount=next(route for route in app.routes if getattr(route,'path',None)=='/static')
    assert isinstance(mount.app,CompressedStaticFiles)
    assert not any(m.cls.__name__=='GZipMiddleware' for m in app.user_middleware)
