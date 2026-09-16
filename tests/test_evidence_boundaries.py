import json
from concurrent.futures import ThreadPoolExecutor
from tests.test_api import setup


def test_pending_solution_never_scheduled(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    async def pending(q):
        return dict(answer='', explanation='题干条件缺失', valid=False, status='pending')
    gateway.solve = pending
    c.post(f'/api/sessions/{sid}/analyze')
    assert c.get('/api/reviews').json()['total'] == 0
    assert app.state.service.study.events(sid, 'q1') == []


def test_legacy_diagnosis_never_becomes_new_learner_state(tmp_path):
    c, app, _, sid = setup(tmp_path)
    s=app.state.store.get_session(sid)
    s['questions'][0]['analysis']=dict(status='confirmed',correct=False,diagnosis='概念混淆',answer='B')
    app.state.store.save_session(s)
    q=c.get(f'/api/sessions/{sid}').json()['questions'][0]
    assert 'diagnosis' not in q['analysis']
    assert c.get('/api/reviews').json()['total'] == 0
    assert c.get('/api/wiki/psa-per-unit').json()['learning']['event_count'] == 0


def test_multi_concept_error_is_associated_fact_not_diagnosis(tmp_path):
    c, app, _, sid=setup(tmp_path)
    c.put(f'/api/sessions/{sid}/questions/q1/links',json={'knowledge_ids':['psa-per-unit','psa-transformer']})
    c.post(f'/api/sessions/{sid}/analyze')
    learning=c.get('/api/wiki/psa-transformer').json()['learning']
    assert '次可用作答' in learning['summary']
    assert '掌握' not in learning['summary']
    assert 'misconception' not in learning


def test_answering_twice_concurrently_records_only_one_event(tmp_path):
    c, app, _, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    study=app.state.service.study
    run=study.start(sid,'q1')
    def answer():
        try:
            study.review(run['id'],'B')
            return 'ok'
        except ValueError:
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: answer(),range(2)))
    assert sorted(results)==['ok','rejected']
    assert len([e for e in study.events(sid,'q1') if e['kind']=='review_answer'])==1


def test_reveal_review_contaminates_other_run(tmp_path):
    c, app, _, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    study=app.state.service.study
    first=study.start(sid,'q1');second=study.start(sid,'q1')
    study.review(first['id'])
    assert study.review(second['id'],'B')['help_kind']=='assisted'


def test_deleted_session_does_not_leave_review_queue(tmp_path):
    c, _, _, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.delete(f'/api/sessions/{sid}')
    assert c.get('/api/reviews').json()['total']==0


def test_repeated_analysis_is_idempotent(tmp_path):
    c, app, gateway, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    count=len(gateway.inputs)
    c.post(f'/api/sessions/{sid}/analyze')
    assert len(gateway.inputs)==count
    assert len(app.state.service.study.events(sid,'q1'))==1


def test_review_waits_for_same_session_chat_or_edit(tmp_path):
    import asyncio
    import httpx
    c, app, gateway, sid=setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    run=app.state.service.study.start(sid,'q1')
    async def scenario():
        started=asyncio.Event(); release=asyncio.Event()
        async def chat(*args):
            started.set()
            await release.wait()
            return {'content':'解释已给出'}
        gateway.chat=chat
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            pending=asyncio.create_task(client.post(f'/api/sessions/{sid}/messages',json={'text':'解释这题'}))
            await started.wait()
            response=await client.post(f'/api/reviews/{run["id"]}/answer',json={'answer':'B'})
            release.set()
            await pending
            assert response.status_code==409
    asyncio.run(scenario())
