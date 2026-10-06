from pathlib import Path
import shutil
import subprocess

import pytest


SW = Path(__file__).resolve().parents[1] / 'app/static/sw.js'


@pytest.fixture(scope='module')
def worker_harness(tmp_path_factory):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required for Service Worker runtime tests')
    script = tmp_path_factory.mktemp('sw-runtime') / 'guard.js'
    script.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const unhandled = [];
process.on('unhandledRejection', error => unhandled.push(error));

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

function dispatch(request, options = {}) {
  const handlers = {};
  const calls = [];
  const lifetimes = [];
  const origin = options.origin || 'https://wealth.example';
  let response, dispatching = true;
  const cache = {
    put(key, clone) {
      calls.push(['put', key, clone]);
      return options.put ? options.put(key, clone) : Promise.resolve();
    },
  };
  const context = {
    URL, Response, console,
    self: {location: {origin}, addEventListener: (type, handler) => {handlers[type] = handler;}},
    fetch(key) {
      calls.push(['fetch', key]);
      return options.network;
    },
    caches: {
      open(name) {calls.push(['open', name]); return options.open ? options.open() : Promise.resolve(cache);},
      match(key) {calls.push(['match', key]); return Promise.resolve(options.match?.(key));},
    },
  };
  vm.runInNewContext(fs.readFileSync(process.argv[2], 'utf8'), context, {filename: 'sw.js'});
  handlers.fetch({request,
    respondWith(promise) { assert.equal(response, undefined); response = promise; },
    waitUntil(promise) {
      assert.equal(dispatching, true, 'lifetime registration must occur during dispatch');
      // The browser owns and observes waitUntil promises, including rejections.
      lifetimes.push(Promise.allSettled([promise]).then(results => results[0]));
    },
  });
  dispatching = false;
  return {response, calls, lifetimes};
}

const bypassRequests = {
  chrome: ['chrome-extension://extension-id/icon.png', 'GET'],
  moz: ['moz-extension://extension-id/icon.png', 'GET'],
  data: ['data:text/plain,hello', 'GET'],
  blob: ['blob:https://wealth.example/blob-id', 'GET'],
  cross: ['https://other.example/icon.png', 'GET'],
  crossApi: ['https://other.example/api/accounts', 'GET'],
  otherPort: ['https://wealth.example:8443/icon.png', 'GET'],
  httpOriginMismatch: ['http://wealth.example/icon.png', 'GET'],
  api: ['https://wealth.example/api/accounts?owner=A', 'GET'],
  js: ['https://wealth.example/static/wealth.js?v=1.3.0', 'GET'],
  css: ['https://wealth.example/static/wealth.css?v=1.3.0', 'GET'],
  post: ['https://wealth.example/dashboard', 'POST'],
  head: ['https://wealth.example/icon.png', 'HEAD'],
};

async function run(scenario) {
  const request = {url: 'https://wealth.example/static/icon-192.png', method: 'GET', mode: 'cors'};
  const networkError = new Error('network unavailable');
  if (scenario.startsWith('bypass:')) {
    const [, kind, outcome] = scenario.split(':');
    const [url, method] = bypassRequests[kind];
    const direct = {...request, url, method, mode: 'navigate'};
    const network = new Response('direct network', {status: 200});
    const event = dispatch(direct, {network: outcome === 'failure' ? Promise.reject(networkError) : Promise.resolve(network)});
    if (outcome === 'failure') await assert.rejects(event.response, error => error === networkError);
    else assert.equal(await event.response, network);
    assert.deepEqual(event.calls, [['fetch', direct]]);
    assert.equal(event.lifetimes.length, 0);
    return;
  }

  if (['success', 'httpSuccess', 'navigationSuccess', 'putFailure', 'openFailure'].includes(scenario)) {
    if (scenario === 'httpSuccess') request.url = 'http://wealth.example/static/icon-192.png';
    if (scenario === 'navigationSuccess') {request.url = 'https://wealth.example/dashboard'; request.mode = 'navigate';}
    const network = deferred(), write = deferred();
    const cacheError = new Error('cache write rejected');
    const event = dispatch(request, {origin: scenario === 'httpSuccess' ? 'http://wealth.example' : undefined,
      network: network.promise, put: () => write.promise,
      open: scenario === 'openFailure' ? () => Promise.reject(cacheError) : undefined});
    assert.deepEqual(event.calls, [['fetch', request]], 'network must start before cache access');
    assert.equal(event.lifetimes.length, 1);
    let settled = false;
    event.lifetimes[0].then(() => {settled = true;});
    const original = new Response('fresh network body', {status: 200});
    network.resolve(original);
    assert.equal(await event.response, original);
    // The successful response is readable while put remains pending.
    assert.equal(await original.text(), 'fresh network body');
    if (scenario !== 'openFailure') assert.equal(settled, false);
    assert.equal(event.calls[1][0], 'open');
    assert.equal(event.calls[1][1], 'wealth-cache-v1.3.0');
    const putCall = event.calls.find(call => call[0] === 'put');
    if (scenario === 'openFailure') {
      assert.equal(putCall, undefined);
      const lifetime = await event.lifetimes[0];
      assert.equal(lifetime.status, 'rejected');
      assert.equal(lifetime.reason, cacheError);
      assert.equal(event.calls.filter(call => call[0] === 'match').length, 0);
      return;
    }
    assert.ok(putCall);
    assert.equal(putCall[1], request);
    assert.notEqual(putCall[2], original);
    assert.equal(await putCall[2].text(), 'fresh network body');
    if (scenario === 'putFailure') write.reject(cacheError);
    else write.resolve();
    const lifetime = await event.lifetimes[0];
    assert.equal(lifetime.status, scenario === 'putFailure' ? 'rejected' : 'fulfilled');
    if (scenario === 'putFailure') assert.equal(lifetime.reason, cacheError);
    assert.equal(event.calls.filter(call => call[0] === 'match').length, 0);
    return;
  }

  if (scenario === 'non200') {
    const network = new Response('not found', {status: 404});
    const event = dispatch(request, {network: Promise.resolve(network)});
    assert.equal(await event.response, network);
    assert.deepEqual(event.calls, [['fetch', request]]);
    assert.equal((await event.lifetimes[0]).status, 'fulfilled');
    return;
  }

  const navigation = scenario.startsWith('navigation');
  if (navigation) {request.url = 'https://wealth.example/page'; request.mode = 'navigate';}
  const hit = new Response('cached content', {status: 200});
  const hitKey = scenario === 'cached' || scenario === 'navigationRequest' ? request :
    scenario === 'navigationRoot' ? '/' : scenario === 'navigationDashboard' ? '/dashboard' : null;
  const event = dispatch(request, {network: Promise.reject(networkError), match: key => key === hitKey ? hit : undefined});
  const response = await event.response;
  if (hitKey) assert.equal(response, hit);
  else {
    assert.equal(response.status, 503);
    assert.equal(response.statusText, 'Service Unavailable');
    assert.equal(response.headers.get('Content-Type'), 'text/plain; charset=utf-8');
    assert.ok((await response.text()).includes('오프라인'));
  }
  const expectedKeys = !navigation || scenario === 'navigationRequest' ? [request] :
    scenario === 'navigationRoot' ? [request, '/'] : [request, '/', '/dashboard'];
  assert.deepEqual(event.calls, [['fetch', request], ...expectedKeys.map(key => ['match', key])]);
  assert.equal((await event.lifetimes[0]).status, 'fulfilled');
}

(async () => {
  await run(process.argv[3]);
  await new Promise(setImmediate);
  await new Promise(setImmediate);
  assert.deepEqual(unhandled, [], 'no floating/unhandled cache write rejection');
})().catch(error => {console.error(error); process.exitCode = 1;});
''', encoding='utf-8')
    return node, script


BYPASS = ['chrome', 'moz', 'data', 'blob', 'cross', 'crossApi', 'otherPort',
          'httpOriginMismatch', 'api', 'js', 'css', 'post', 'head']
SCENARIOS = [f'bypass:{kind}:{outcome}' for kind in BYPASS for outcome in ['success', 'failure']] + [
    'success', 'httpSuccess', 'navigationSuccess', 'putFailure', 'openFailure', 'non200',
    'cached', 'staticMissing', 'navigationRequest', 'navigationRoot',
    'navigationDashboard', 'navigationMissing',
]


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_service_worker_cache_strategy(worker_harness, scenario):
    node, script = worker_harness
    result = subprocess.run([node, str(script), str(SW), scenario],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
