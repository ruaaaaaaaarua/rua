import asyncio
import copy
import json

import httpx

from app.providers import ProviderError
from tests.test_api import setup, QUESTION


def test_pipeline_solves_first_during_ocr_and_keeps_it_interactive(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'] = []
    s['attachments'] = [dict(id='image', name='test.jpg', mime='image/jpeg', extracted=False)]
    (app.state.store.attachments / 'image').write_bytes(b'fake-image')
    app.state.store.save_session(s)

    async def scenario():
        recognized = asyncio.Event()
        release = asyncio.Event()
        solved = asyncio.Event()

        async def extract(images):
            yield json.dumps(dict(type='question', question=QUESTION)) + '\n'
            recognized.set()
            await release.wait()
            yield json.dumps(dict(type='question', question={**QUESTION, 'number': 2})) + '\n'
            yield '{"type":"done"}\n'

        async def solve(q):
            solved.set()
            return dict(answer='B', explanation='依据', valid=True, status='confirmed')

        gateway.stream_extract = extract
        gateway.solve = solve
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
            started = await c.post(f'/api/sessions/{sid}/process')
            assert started.status_code == 200
            assert started.json()['processing'] is True
            await asyncio.wait_for(recognized.wait(), 1)
            await asyncio.wait_for(solved.wait(), 1)
            progress = (await c.get(f'/api/sessions/{sid}')).json()
            q = progress['questions'][0]
            assert q['analysis']['correct'] is False
            assert progress['processing'] is True
            assert (await c.post(f'/api/sessions/{sid}/process')).status_code == 200
            assert (await c.patch(f'/api/sessions/{sid}/questions/{q["id"]}', json={'text': 'changed'})).status_code == 409
            assert (await c.delete(f'/api/sessions/{sid}')).status_code == 409
            assert (await c.post(f'/api/sessions/{sid}/questions/{q["id"]}/reveal')).status_code == 200
            assert (await c.post(f'/api/sessions/{sid}/questions/{q["id"]}/hint')).status_code == 200
            release.set()
            await app.state.jobs.wait(sid)
            result = (await c.get(f'/api/sessions/{sid}')).json()
            assert not result['processing']
            assert len(result['questions']) == 2
            assert result['questions'][0]['help_seen']
            assert any(m['type'] == 'hint' for m in result['messages'])
    asyncio.run(scenario())


def test_small_batches_fallback_only_missing_items_and_skip_confirmed(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'] = [{**copy.deepcopy(QUESTION), 'id': f'q{i}', 'number': i} for i in range(1, 8)]
    app.state.store.save_session(s)
    batches, singles = [], []

    async def batch(qs):
        batches.append([q['id'] for q in qs])
        return [dict(index=0, answer='B', explanation='批量依据', status='confirmed', valid=True)]

    async def solve(q):
        singles.append(q['id'])
        return dict(answer='B', explanation='单题依据', status='confirmed', valid=True)

    gateway.solve_batch, gateway.solve = batch, solve

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
            response = await c.post(f'/api/sessions/{sid}/process')
            assert response.status_code == 200
            await app.state.jobs.wait(sid)
            result = (await c.get(f'/api/sessions/{sid}')).json()
            assert all(q['analysis']['status'] == 'confirmed' for q in result['questions'])
            assert batches and all(len(b) <= 3 for b in batches)
            assert singles[0] == 'q1'
            assert not any(b[0] in singles for b in batches)
            total = len(singles) + len(batches)
            await c.post(f'/api/sessions/{sid}/process')
            await app.state.jobs.wait(sid)
            assert len(singles) + len(batches) == total
    asyncio.run(scenario())


def test_stream_chat_persists_complete_reply_and_marks_interrupted_help(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')

    async def stream(*args):
        yield '第一段'
        yield '第二段'

    gateway.stream_chat = stream
    response = c.post(f'/api/sessions/{sid}/messages-stream', json={'text': '解释一下', 'question_id': 'q1'})
    assert response.status_code == 200
    assert 'event: delta' in response.text and '第一段' in response.text
    assert 'event: done' in response.text
    s = app.state.store.get_session(sid)
    assert s['messages'][-1]['content'] == '第一段第二段'
    assert s['messages'][-1]['question_id'] == 'q1'
    assert s['questions'][0]['help_seen']

    async def interrupted(*args):
        yield '不完整的讲解'
        raise ProviderError('中断')

    gateway.stream_chat = interrupted
    response = c.post(f'/api/sessions/{sid}/messages-stream', json={'text': '再解释', 'question_id': 'q1'})
    assert 'event: error' in response.text and 'event: done' not in response.text
    assert not any(m['content'] == '不完整的讲解' for m in app.state.store.get_session(sid)['messages'])


def test_stream_hint_buffers_and_checks_before_any_delta(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.post(f'/api/sessions/{sid}/questions/q1/hint')

    async def dangerous(*args):
        return {'content': '正确答案是 B'}

    async def must_not_stream(*args):
        raise AssertionError('hint must be buffered')
        yield ''

    gateway.chat, gateway.stream_chat = dangerous, must_not_stream
    result = c.post(f'/api/sessions/{sid}/messages-stream', json={'text': '再提示一点', 'question_id': 'q1'})
    assert 'event: done' in result.text
    assert '正确答案是 B' not in result.text


def test_background_completion_during_chat_preserves_both_results(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'].append({**copy.deepcopy(QUESTION), 'id': 'q2', 'number': 2})
    app.state.store.save_session(s)

    async def scenario():
        waiting = asyncio.Event()
        release_solve = asyncio.Event()
        chat_started = asyncio.Event()
        release_chat = asyncio.Event()

        async def solve(q):
            if q['id'] == 'q2':
                waiting.set()
                await release_solve.wait()
            return dict(answer='B', explanation='依据', valid=True, status='confirmed')

        async def stream(*args):
            yield '正在解释'
            chat_started.set()
            await release_chat.wait()
            yield '，完成。'

        gateway.solve, gateway.stream_chat = solve, stream
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
            await c.post(f'/api/sessions/{sid}/process')
            await asyncio.wait_for(waiting.wait(), 1)
            response = asyncio.create_task(c.post(f'/api/sessions/{sid}/messages-stream', json={'text': '解释', 'question_id': 'q1'}))
            await asyncio.wait_for(chat_started.wait(), 1)
            release_solve.set()
            await app.state.jobs.wait(sid)
            release_chat.set()
            assert 'event: done' in (await response).text
            s = (await c.get(f'/api/sessions/{sid}')).json()
            assert s['questions'][1]['analysis']['status'] == 'confirmed'
            assert s['questions'][0]['help_seen']
            assert s['messages'][-1]['content'] == '正在解释，完成。'
            assert s['status'] == 'ready' and not s['processing']
    asyncio.run(scenario())


def test_restart_clears_persisted_processing_flag(tmp_path):
    from app.store import Store
    store = Store(tmp_path)
    s = store.create_session()
    s.update(processing=True, status='ready', job_phase='solving')
    store.save_session(s)
    restored = Store(tmp_path).get_session(s['id'])
    assert restored['processing'] is False
    assert restored['status'] == 'error'
    assert restored['job_phase'] is None


def test_batch_pending_row_gets_one_individual_retry(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'].append({**copy.deepcopy(QUESTION), 'id': 'q2', 'number': 2})
    singles = []

    async def batch(qs):
        return [dict(index=0, answer='', explanation='不确定', status='pending', valid=False),
                dict(index=1, answer='B', explanation='依据', status='confirmed', valid=True)]

    async def solve(q):
        singles.append(q['id'])
        return dict(answer='B', explanation='单题重新确认', valid=True, status='confirmed')

    gateway.solve_batch, gateway.solve = batch, solve
    asyncio.run(app.state.service.solve_group(s, s['questions'], gateway))
    assert singles == ['q1']
    assert all(q['analysis']['status'] == 'confirmed' for q in s['questions'])


def test_pipeline_failure_keeps_success_and_retries_only_failure(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'].append({**copy.deepcopy(QUESTION), 'id': 'q2', 'number': 2})
    app.state.store.save_session(s)
    calls = []

    async def solve(q):
        calls.append(q['id'])
        if q['id'] == 'q2' and calls.count('q2') == 1:
            raise ProviderError('服务限流')
        return dict(answer='B', explanation='依据', valid=True, status='confirmed')

    gateway.solve = solve

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
            await c.post(f'/api/sessions/{sid}/process')
            await app.state.jobs.wait(sid)
            failed = (await c.get(f'/api/sessions/{sid}')).json()
            assert failed['status'] == 'error'
            assert failed['questions'][0]['analysis']['status'] == 'confirmed'
            assert failed['questions'][1]['analysis']['status'] == 'pending'
            await c.post(f'/api/sessions/{sid}/process')
            await app.state.jobs.wait(sid)
            assert (await c.get(f'/api/sessions/{sid}')).json()['status'] == 'ready'
            assert calls == ['q1', 'q2', 'q2']
    asyncio.run(scenario())


def test_incomplete_question_never_becomes_confirmed_or_review_evidence(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    q = s['questions'][0]
    q['incomplete'] = True
    q['recognition_note'] = '页底选项被截断'
    asyncio.run(app.state.service.solve_group(s, [q], gateway))
    assert q['analysis']['status'] == 'pending'
    assert q['analysis']['correct'] is None
    assert not gateway.inputs
    assert app.state.service.study.events(sid, q['id']) == []


def test_single_visible_option_requires_confirmation_not_an_answer(tmp_path):
    _, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    q = s['questions'][0]
    q['options'] = q['options'][:1]
    app.state.service.save_solution(s, q, dict(answer='A', valid=True, status='confirmed'), [])
    assert q['analysis']['status'] == 'pending'
    assert q['analysis']['correct'] is None


def test_editing_does_not_silently_acknowledge_missing_material(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'][0]['incomplete'] = True
    app.state.store.save_session(s)
    changed = c.patch(f'/api/sessions/{sid}/questions/q1', json={'text': '只修正一个字'}).json()
    assert changed['questions'][0]['incomplete'] is True
    fixed = c.patch(f'/api/sessions/{sid}/questions/q1', json={
        'text': '已根据原图补全的题目', 'completeness_confirmed': True,
    })
    assert fixed.status_code == 200
    assert fixed.json()['questions'][0]['incomplete'] is False
