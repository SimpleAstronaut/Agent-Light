import asyncio
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import web
from jsonschema import ValidationError
from .core import Store, Conflict, SCHEMA
from .locking import ProcessLock
from .serial_link import SerialWorker


def application(cfg):
    store = Store(cfg['database'], cfg['completedHoldSeconds'], cfg['brightness'])
    link = SerialWorker(cfg, store)
    token = Path(cfg['tokenFile']).read_text().strip()
    budget = [time.monotonic(), 0]

    @web.middleware
    async def guard(request, handler):
        if not hmac.compare_digest(request.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
            raise web.HTTPUnauthorized()
        if request.headers.get('Origin'):
            raise web.HTTPForbidden()
        if time.monotonic() - budget[0] >= 1:
            budget[:] = [time.monotonic(), 0]
        budget[1] += 1
        if budget[1] > 200:
            raise web.HTTPTooManyRequests(headers={'Retry-After': '1'})
        try:
            return await handler(request)
        except Conflict:
            raise web.HTTPConflict(text='EVENT_ID_CONFLICT')
        except (ValueError, KeyError, TypeError, ValidationError):
            raise web.HTTPUnprocessableEntity(text='INVALID_REQUEST') from None

    async def health(request):
        return web.json_response(dict(schema_version=1, usb_protocol=1, database='ready',
            event_types=SCHEMA['oneOf'][0]['properties']['type']['enum'] + ['runtime_ready'],
            sources={'dsh': 'unverified', 'codex': 'reserved'}))

    async def events(request):
        e = await request.json()
        result = store.apply(e)
        return web.json_response(result, status=202 if result['status'] == 'pending_identity' else 200)

    async def batch(request):
        es = await request.json()
        if not isinstance(es, list) or not 1 <= len(es) <= 32 or any(not isinstance(e, dict) or e.get('type') == 'runtime_ready' for e in es):
            raise ValueError()
        return web.json_response([store.apply(e) for e in es])

    async def heartbeat(request):
        store.heartbeat(await request.json())
        return web.json_response({'status': 'accepted'})

    async def status(request):
        store.tick()
        sources = {k: {**v, 'lease_expired': time.monotonic()-store.leases.get(k, 0)>15} for k,v in store.s['sources'].items()}
        return web.json_response({**store.s, 'sources': sources, 'connected': link.connected,
                                  'acked_revision': link.acked_revision, 'serial_diagnostic': link.diagnostic})

    async def clear(request):
        store.clear()
        return web.json_response({'status': 'cleared'})

    async def test(request):
        link.test_until = time.monotonic() + 3
        return web.json_response({'status': 'scheduled'})

    async def lifecycle(app):
        lock = ProcessLock(cfg['database'] + '.lock')
        task = asyncio.create_task(link.run())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        store.db.close()
        lock.close()

    app = web.Application(middlewares=[guard], client_max_size=65536)
    app.cleanup_ctx.append(lifecycle)
    for method, path, handler in [('GET','health',health),('GET','status',status),
            ('POST','events',events),('POST','events/batch',batch),('POST','producers/heartbeat',heartbeat),
            ('POST','display/clear',clear),('POST','display/test',test)]:
        app.router.add_route(method, '/v1/' + path, handler)
    return app


def serve(cfg):
    u = urlsplit(cfg['endpoint'])
    if u.scheme != 'http' or u.hostname != '127.0.0.1' or u.path not in ('', '/') or u.username or u.query or u.fragment:
        raise ValueError('LOOPBACK_ENDPOINT_REQUIRED')
    if not 20 <= cfg['brightness'] <= 100 or cfg['completedHoldSeconds'] < 0:
        raise ValueError('INVALID_DISPLAY_CONFIG')
    web.run_app(application(cfg), host='127.0.0.1', port=u.port or 17321, access_log=None)
