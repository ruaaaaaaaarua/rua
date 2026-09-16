import copy
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.store import Store
from app.providers import ModelGateway
from tests.test_api import setup, QUESTION


def test_daily_names_are_unique_reset_and_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr('app.store.now', lambda: '2026-09-15T15:59:00+00:00')
    store=Store(tmp_path)
    first=store.create_session()
    assert first['title']=='电力系统分析1 · 260915'
    store.delete_session(first['id'])
    assert store.create_session()['title']=='电力系统分析2 · 260915'
    monkeypatch.setattr('app.store.now', lambda: '2026-09-15T16:01:00+00:00')
    assert store.create_session()['title']=='电力系统分析1 · 260916'
    assert store.create_session('自己的标题')['title']=='自己的标题'


def test_concurrent_daily_names(tmp_path):
    store=Store(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        names=list(pool.map(lambda _:store.create_session()['title'], range(8)))
    assert len(set(names))==8


def test_hint_is_scoped_cached_and_records_help_without_replacing_answer(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    response=c.post(f'/api/sessions/{sid}/questions/q1/hint')
    assert response.status_code==200
    msg=response.json()['messages'][-1]
    assert msg['type']=='hint' and msg['question_id']=='q1'
    assert gateway.inputs[-1]['hint_only'] is True
    count=len(gateway.inputs)
    assert c.post(f'/api/sessions/{sid}/questions/q1/hint').status_code==200
    assert len(gateway.inputs)==count
    q=c.post(f'/api/sessions/{sid}/questions/q1/retry',json={'answer':'B'}).json()['questions'][0]
    assert q['user_answer']=='A' and q['attempts'][-1]['help_kind']=='assisted'


def test_question_chats_and_references_do_not_cross_threads(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    s=app.state.store.get_session(sid)
    s['questions'].append(dict(copy.deepcopy(QUESTION),id='q2',revision=1))
    s['references']=[dict(id='r1',text='PRIVATE_REFERENCE_Q1',question_id='q1')]
    app.state.store.save_session(s)
    c.post(f'/api/sessions/{sid}/messages',json={'text':'PRIVATE_Q1','question_id':'q1'})
    c.post(f'/api/sessions/{sid}/messages',json={'text':'QUESTION_Q2','question_id':'q2'})
    context=gateway.inputs[-1]
    assert 'PRIVATE_Q1' not in json.dumps(context)
    assert 'PRIVATE_REFERENCE_Q1' not in json.dumps(context)
    assert [q['id'] for q in context['questions']]==['q2']
    c.post(f'/api/sessions/{sid}/messages',json={'text':'PUBLIC_CHAT'})
    assert 'PRIVATE_Q1' not in json.dumps(gateway.inputs[-1]['history'])


def test_default_parallelism_is_bounded_and_explicit_limit_wins():
    settings=dict(profiles=[dict(id='p',model='test',base_url='https://example.com',api_key='x')],tasks={'solve':'p'})
    gateway=ModelGateway(settings)
    assert gateway.parallel_for('solve')==2
    settings['profiles'][0]['parallel']=1
    assert ModelGateway(settings).parallel_for('solve')==1


def test_followup_stays_hint_only_until_solution_revealed(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.post(f'/api/sessions/{sid}/questions/q1/hint')
    c.post(f'/api/sessions/{sid}/messages',json={'text':'再说一点','question_id':'q1'})
    assert gateway.inputs[-1]['hint_only'] is True
    c.post(f'/api/sessions/{sid}/questions/q1/reveal')
    c.post(f'/api/sessions/{sid}/messages',json={'text':'详细解释','question_id':'q1'})
    assert gateway.inputs[-1]['hint_only'] is False


def test_hint_rejects_explicit_answer_disclosure(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    async def revealing(*args): return {'content':'正确答案是 B，直接选它。'}
    gateway.chat=revealing
    c.post(f'/api/sessions/{sid}/analyze')
    result=c.post(f'/api/sessions/{sid}/questions/q1/hint').json()
    assert '正确答案是 B' not in result['messages'][-1]['content']


def test_revised_question_excludes_old_thread_and_gets_fresh_hint(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.post(f'/api/sessions/{sid}/messages',json={'text':'OLD_QUESTION_DISCUSSION','question_id':'q1'})
    c.patch(f'/api/sessions/{sid}/questions/q1',json={'text':'标幺值的新题干'})
    c.post(f'/api/sessions/{sid}/analyze')
    response=c.post(f'/api/sessions/{sid}/questions/q1/hint')
    assert response.status_code==200
    assert 'OLD_QUESTION_DISCUSSION' not in json.dumps(gateway.inputs[-1])


def test_progress_is_readable_before_all_solutions_finish(tmp_path):
    import httpx
    c,app,gateway,sid=setup(tmp_path)
    s=app.state.store.get_session(sid)
    s['questions'].append(dict(copy.deepcopy(QUESTION),id='q2',revision=1))
    app.state.store.save_session(s)
    async def scenario():
        second=asyncio.Event();release=asyncio.Event()
        async def solve(q):
            if q['id']=='q2':
                second.set();await release.wait()
            return dict(answer='B',explanation='测试',status='confirmed',valid=True)
        gateway.solve=solve
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            work=asyncio.create_task(client.post(f'/api/sessions/{sid}/analyze'))
            await second.wait()
            progress=(await client.get(f'/api/sessions/{sid}')).json()
            release.set();await work
            assert progress['status']=='analyzing'
            assert progress['questions'][0]['analysis']['correct'] is False
            assert 'analysis' not in progress['questions'][1]
    asyncio.run(scenario())


def test_correcting_transcript_does_not_erase_recent_hint_exposure(tmp_path):
    c,app,_,sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.post(f'/api/sessions/{sid}/questions/q1/hint')
    c.patch(f'/api/sessions/{sid}/questions/q1',json={'user_answer':'B'})
    c.post(f'/api/sessions/{sid}/analyze')
    run=c.post('/api/reviews/start',json={'session_id':sid,'question_id':'q1'}).json()
    assert run['help_kind']=='assisted'
