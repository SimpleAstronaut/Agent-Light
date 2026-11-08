import asyncio
import hmac
import json
import time
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from aiohttp import web
from jsonschema import ValidationError
from .core import Store, Conflict, SourceError, SCHEMA
from .locking import ProcessLock
from .serial_link import SerialWorker
from .devices import DeviceScanner
from .config import ConfigRepository, ConfigError
SERIAL_TASK = web.AppKey('serial_task', asyncio.Task)


def application(cfg, *, config_path=None):
    cfg = dict(cfg)
    store = link = repository = scanner = None
    token = ''
    stopping = False
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
        if stopping and request.method not in ('GET', 'HEAD'):
            return error_response('SERVICE_STOPPING', 503)
        try:
            return await handler(request)
        except (ConfigError, SourceError) as exc:
            code = str(exc)
            status = {'CONFIG_PATH_REQUIRED': 503, 'CONFIG_SAVE_FAILED': 500,
                      'CONFIG_CHANGED_EXTERNALLY': 409, 'DISPLAY_TEST_RUNNING': 409,
                      'SERVICE_STOPPING': 503, 'DEVICE_BUSY': 409, 'DEVICE_NOT_READY': 409,
                      'DEVICE_NOT_UNIQUE': 409, 'DEVICE_NOT_FOUND': 404, 'DEVICE_IDENTITY_MISMATCH': 409,
                      'DEVICE_SCAN_TIMEOUT': 504, 'DEVICE_SCAN_FAILED': 500, 'PRODUCER_DISABLED': 409,
                      'PRODUCER_NOT_FOUND': 404, 'PRODUCER_STILL_REPORTING': 409, 'SOURCE_STATE_CHANGED': 409}.get(code, 422)
            return error_response(code, status)
        except Conflict:
            raise web.HTTPConflict(text='EVENT_ID_CONFLICT')
        except (ValueError, KeyError, TypeError, ValidationError):
            if request.path in ('/v1/config/display','/v1/display/test','/v1/device/connect',
                                '/v1/device/disconnect','/v1/devices','/v1/producers/disable','/v1/producers/enable'):
                return error_response('INVALID_REQUEST',422)
            raise web.HTTPUnprocessableEntity(text='INVALID_REQUEST') from None

    def error_response(code, status):
        return web.json_response({'error': {'code': code}}, status=status)

    async def health(request):
        try:
            service_version = version('agent-light')
        except PackageNotFoundError:
            service_version = 'unknown'
        return web.json_response(dict(schema_version=1, usb_protocol=1, database='ready',
            desktop_api=1, service_version=service_version,
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
                                  'acked_revision': link.acked_revision, 'serial_diagnostic': link.diagnostic, 'device': link.snapshot(),
                                  'display_test': link.display_test, 'producers': store.producers()})

    async def clear(request):
        store.clear()
        return web.json_response({'status': 'cleared'})

    async def test(request):
        if await request.json() != {}:
            raise ConfigError('INVALID_REQUEST')
        async with repository.lock:
            test_id = link.start_test()
        return web.json_response({'status': 'scheduled', 'test_id': test_id})

    def display_values():
        return {k: cfg[k] for k in ('brightness', 'completedHoldSeconds')}

    async def display_config(request):
        if request.method == 'GET':
            return web.json_response(display_values())
        patch = await request.json()
        def check():
            if link.test_running:
                raise ConfigError('DISPLAY_TEST_RUNNING')
        def publish(candidate):
            cfg.update(candidate)
            link.cfg.update(candidate)
            store.hold = cfg['completedHoldSeconds']
            store.brightness = cfg['brightness']
        await repository.update(patch, allowed=('brightness', 'completedHoldSeconds'),
                                publish=publish, check=check)
        return web.json_response(dict(status='applied', configuration_saved=True,
                                      backend_applied=True, **display_values()))

    async def devices(request):
        include = request.query.get('include_all', 'false')
        if include not in ('true', 'false'):
            raise ConfigError('INVALID_REQUEST')
        return web.json_response({'devices': await scanner.scan(cfg, include == 'true')})

    async def connect(request):
        body = await request.json()
        if (not isinstance(body, dict) or set(body) - {'mode','port','serial_number'}
                or body.get('mode') not in ('auto', 'manual')
                or (body.get('serial_number') is not None and not isinstance(body['serial_number'], str))):
            raise ConfigError('INVALID_REQUEST')
        if body['mode'] == 'auto' and body.get('port') is not None:
            raise ConfigError('INVALID_REQUEST')
        if body['mode'] == 'manual' and (not isinstance(body.get('port'), str) or not body['port']):
            raise ConfigError('INVALID_REQUEST')
        candidates = await scanner.scan(cfg, True)
        serial_number = body.get('serial_number')
        if body['mode'] == 'manual':
            candidate = next((p for p in candidates if p['port'] == body['port']), None)
            if candidate is None:
                raise ConfigError('DEVICE_NOT_FOUND')
            if serial_number is not None and serial_number != candidate['serial_number']:
                raise ConfigError('DEVICE_IDENTITY_MISMATCH')
        else:
            candidates = [p for p in candidates if p['vid'] == cfg['vid'] and p['pid'] == cfg['pid']
                          and (serial_number is None or p['serial_number'] == serial_number)]
            if len(candidates) != 1:
                raise ConfigError('DEVICE_NOT_UNIQUE' if candidates else 'DEVICE_NOT_FOUND')
        patch = dict(port=body.get('port') if body['mode']=='manual' else None, serialNumber=serial_number)
        def publish(candidate):
            cfg.update(candidate)
            if not repository.stopping and not stopping:
                link.connect(candidate)
        await repository.update(patch, allowed=('port','serialNumber'), publish=publish, check=link.reserve_control)
        return web.json_response({'status':'connecting', 'configuration_saved':True}, status=202)

    async def disconnect(request):
        async with repository.lock:
            release = link.reserve_control()
            try:
                link.disconnect()
            finally:
                release()
        return web.json_response({'status':'disconnecting','enabled':False}, status=202)

    async def manage_source(request):
        result = store.manage_source(await request.json(), request.path.endswith('/enable'))
        return web.json_response(result)

    async def lifecycle(app):
        nonlocal store, link, repository, scanner, token, stopping
        lock = ProcessLock(cfg['database'] + '.lock')
        task = None
        try:
            token = Path(cfg['tokenFile']).read_text().strip()
            if not token:
                raise ValueError('TOKEN_MISSING')
            store = Store(cfg['database'], cfg['completedHoldSeconds'], cfg['brightness'])
            repository = ConfigRepository(config_path, cfg)
            scanner = DeviceScanner()
            link = SerialWorker(cfg, store)
            task = asyncio.create_task(link.run())
            app[SERIAL_TASK] = task
            yield
        finally:
            stopping = True
            try:
                if repository is not None:
                    await repository.close()
            finally:
                try:
                    try:
                        if task is not None:
                            link.request_stop()
                            await task
                    finally:
                        if scanner is not None:
                            await scanner.close()
                finally:
                    try:
                        if store is not None:
                            store.db.close()
                    finally:
                        lock.close()

    async def begin_shutdown(app):
        nonlocal stopping
        stopping = True


    app = web.Application(middlewares=[guard], client_max_size=65536)
    app.cleanup_ctx.append(lifecycle)
    app.on_shutdown.append(begin_shutdown)
    for method, path, handler in [('GET','health',health),('GET','status',status),
            ('POST','events',events),('POST','events/batch',batch),('POST','producers/heartbeat',heartbeat),
            ('POST','display/clear',clear),('POST','display/test',test),
            ('GET','devices',devices), ('POST','device/connect',connect), ('POST','device/disconnect',disconnect),
            ('POST','producers/disable',manage_source), ('POST','producers/enable',manage_source),
            ('GET','config/display',display_config),('PATCH','config/display',display_config)]:
        app.router.add_route(method, '/v1/' + path, handler)
    return app


def serve(cfg, *, config_path=None):
    from .runtime import ServiceRuntime
    ServiceRuntime(cfg, config_path=config_path).run_blocking()
