"""Isolated real HTTP/SQLite fixture for Playwright; never opens ./data."""
import asyncio
import copy
import tempfile

import uvicorn

from app.main import create_app
from tests.test_api import Gateway, QUESTION


def main():
    with tempfile.TemporaryDirectory(prefix='grid-browser-') as directory:
        gateway = Gateway()
        app = create_app(directory, lambda _: gateway)
        # Only the test port needs an alias; the production guard remains unchanged.
        @app.middleware('http')
        async def test_origin_alias(request, call_next):
            request.scope['headers'] = [
                (key, b'http://127.0.0.1:5173' if key == b'origin' and
                 value == b'http://127.0.0.1:18765' else value)
                for key, value in request.scope['headers']
            ]
            return await call_next(request)

        store, service = app.state.store, app.state.service
        for width in (1440, 390):
            session = store.create_session(f'工程回归测试 {width}')
            session['questions'] = [dict(copy.deepcopy(QUESTION), id='q1', revision=1,
                                         text=f'标幺值的基准选择题（{width}）')]
            store.save_session(session)
            asyncio.run(service.analyze(session))
        uvicorn.run(app, host='127.0.0.1', port=18765, log_level='warning')


if __name__ == '__main__':
    main()
