import copy
import json

from fastapi.testclient import TestClient
from app.main import create_app


QUESTION = dict(number=1, kind='single', text='标幺值的基准选择题', options=[
    dict(key='A', text='选项甲'), dict(key='B', text='选项乙')],
    user_answer='A', subject='电力系统分析', chapter='基础', knowledge='标幺值')


class Gateway:
    def __init__(self):
        self.inputs = []
    async def solve(self, q):
        self.inputs.append(copy.deepcopy(q))
        return dict(answer='B', explanation='模型测试解答', valid=True, status='confirmed')
    async def extract(self, images):
        return [copy.deepcopy(QUESTION)]
    async def stream_extract(self, images):
        yield json.dumps(dict(type='question', question=QUESTION), ensure_ascii=False) + '\n'
        yield '{"type":"done"}\n'
    async def chat(self, context, text, mode):
        self.inputs.append(context)
        return {'content': '模型测试讲解'}


def setup(tmp_path):
    gateway = Gateway()
    app = create_app(tmp_path, lambda _: gateway)
    c = TestClient(app)
    s = c.post('/api/sessions', json={}).json()
    internal = app.state.store.get_session(s['id'])
    internal['questions'] = [dict(copy.deepcopy(QUESTION), id='q1', revision=1)]
    app.state.store.save_session(internal)
    return c, app, gateway, s['id']


def test_solve_retrieves_then_links_without_diagnosis(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    response = c.post(f'/api/sessions/{sid}/analyze')
    assert response.status_code == 200, response.text
    q = response.json()['questions'][0]
    assert q['links'][0]['knowledge_id'] == 'psa-per-unit'
    assert q['analysis']['correct'] is False
    assert q['analysis']['knowledge_status'] == 'empty'
    assert q['analysis']['citations'] == []
    assert 'diagnosis' not in q['analysis']
    assert gateway.inputs[0]['wiki_context'] == []
    events = app.state.service.study.events(sid, 'q1')
    assert events[0]['help_kind'] == 'unknown'
    assert c.get('/api/reviews').json()['total'] == 1


def test_unanswered_photo_is_solved_without_inventing_answer(tmp_path):
    c, app, _, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s['questions'][0]['user_answer'] = ''
    app.state.store.save_session(s)
    q = c.post(f'/api/sessions/{sid}/analyze').json()['questions'][0]
    assert q['analysis']['status'] == 'confirmed'
    assert q['analysis']['correct'] is None
    assert app.state.service.study.events(sid, 'q1')[0]['kind'] == 'saved'


def test_links_are_personal_and_wiki_is_unchanged(tmp_path):
    c, app, _, sid = setup(tmp_path)
    before = app.state.service.library.catalog()
    response = c.put(f'/api/sessions/{sid}/questions/q1/links',
                     json={'knowledge_ids': ['psa-per-unit', 'psa-transformer']})
    assert response.status_code == 200
    assert len(c.get('/api/wiki/psa-per-unit').json()['questions']) == 1
    assert before == app.state.service.library.catalog()
    assert c.put(f'/api/sessions/{sid}/questions/q1/links',
                 json={'knowledge_ids': ['invented']}).status_code == 422
    assert len(c.get('/api/wiki/psa-per-unit').json()['questions']) == 1
    c.put(f'/api/sessions/{sid}/questions/q1/links', json={'knowledge_ids': []})
    c.post(f'/api/sessions/{sid}/analyze')
    assert c.get('/api/wiki/psa-per-unit').json()['questions'] == []


def test_edit_invalidates_review_and_historical_verdict(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    run = c.post('/api/reviews/start', json={'session_id': sid, 'question_id': 'q1'}).json()
    c.patch(f'/api/sessions/{sid}/questions/q1', json={'text': '新的题干'})
    assert c.get('/api/reviews').json()['total'] == 0
    assert app.state.service.study.events(sid, 'q1') == []
    assert c.post(f'/api/reviews/{run["id"]}/answer', json={'answer': 'B'}).status_code == 400


def test_review_hides_answer_and_rejects_repeat_submission(tmp_path):
    c, _, _, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    run = c.post('/api/reviews/start', json={'session_id': sid, 'question_id': 'q1'}).json()
    assert 'answer' not in run and 'user_answer' not in run['question']
    assert 'explanation' not in run
    assert run['help_kind'] == 'independent'
    result = c.post(f'/api/reviews/{run["id"]}/answer', json={'answer': 'B'}).json()
    assert result['correct'] is True
    assert result['help_kind'] == 'independent'
    assert result['next_due_at']
    assert c.post(f'/api/reviews/{run["id"]}/answer', json={'answer': 'B'}).status_code == 400


def test_review_marks_help_across_panels_and_repeated_runs(tmp_path):
    c, _, _, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    run = c.post('/api/reviews/start', json={'session_id': sid, 'question_id': 'q1'}).json()
    c.post(f'/api/sessions/{sid}/questions/q1/reveal')
    result = c.post(f'/api/reviews/{run["id"]}/answer', json={'answer': 'B'}).json()
    assert result['help_kind'] == 'assisted'
    new = c.post('/api/reviews/start', json={'session_id': sid, 'question_id': 'q1'}).json()
    assert new['help_kind'] == 'assisted'


def test_generated_quiz_and_diagnosis_endpoints_removed(tmp_path):
    c, _, _, sid = setup(tmp_path)
    assert c.post(f'/api/sessions/{sid}/train', json={}).status_code == 404
    assert c.post('/api/demo', json={}).status_code == 404
    assert c.get('/api/framework').json()['subjects'] == ['电力系统分析']


def test_stream_extract_and_retry_does_not_duplicate(tmp_path):
    c, app, _, sid = setup(tmp_path)
    response = c.post(f'/api/sessions/{sid}/upload', files=[('files', ('q.png', b'\x89PNG\r\n\x1a\nfixture', 'image/png'))])
    assert response.status_code == 200
    stream = c.post(f'/api/sessions/{sid}/extract-stream')
    assert 'event: done' in stream.text
    count = len(c.get(f'/api/sessions/{sid}').json()['questions'])
    c.post(f'/api/sessions/{sid}/extract-stream')
    assert len(c.get(f'/api/sessions/{sid}').json()['questions']) == count


def test_cross_site_and_invalid_upload_are_rejected(tmp_path):
    c, _, _, sid = setup(tmp_path)
    assert c.post('/api/sessions', json={}, headers={'origin': 'https://evil.example'}).status_code == 403
    assert c.post(f'/api/sessions/{sid}/upload', files=[('files', ('bad.png', b'not-png', 'image/png'))]).status_code == 400


def test_settings_upgrade_keeps_keys_and_only_three_roles(tmp_path):
    c, app, _, _ = setup(tmp_path)
    app.state.store.save_settings(dict(profiles=[dict(id='p', name='主模型', model='model',
        base_url='https://example.com/v1', api_key='secret')],
        tasks={k:'p' for k in ('vision','solve','chat','generate','verify')}, mode='hint'))
    public = c.get('/api/settings').json()
    assert set(public['tasks']) == {'vision','solve','chat'}
    assert public['mode'] == 'direct'
    assert 'secret' not in json.dumps(public)
    public['profiles'][0]['api_key'] = ''
    assert c.put('/api/settings', json=public).status_code == 200
    assert app.state.store.settings()['profiles'][0]['api_key'] == 'secret'


def test_chat_has_wiki_context_even_before_any_photo(tmp_path):
    c, _, gateway, sid = setup(tmp_path)
    response = c.post(f'/api/sessions/{sid}/messages',
                      json={'text': '解释标幺值', 'knowledge_id': 'psa-per-unit'})
    assert response.status_code == 200
    assert gateway.inputs[-1]['wiki_context'] == []
    assert response.json()['messages'][-1]['knowledge_status'] == 'empty'


def test_retry_keeps_original_answer(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/analyze')
    c.post(f'/api/sessions/{sid}/questions/q1/reveal')
    response = c.post(f'/api/sessions/{sid}/questions/q1/retry', json={'answer':'B'})
    assert response.status_code == 200
    q = response.json()['questions'][0]
    assert q['user_answer'] == 'A'
    assert q['attempts'][-1]['help_kind'] == 'assisted'


def test_partial_stream_retry_rejects_changed_order_without_losing_cached_question(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/upload', files=[('files', ('q.png', b'\x89PNG\r\n\x1a\nfixture', 'image/png'))])
    async def interrupted(images):
        yield json.dumps(dict(type='question', question=QUESTION)) + '\n'
    gateway.stream_extract = interrupted
    assert 'event: error' in c.post(f'/api/sessions/{sid}/extract-stream').text
    cached = c.get(f'/api/sessions/{sid}').json()['questions'][-1]
    async def changed(images):
        yield json.dumps(dict(type='question', question={**QUESTION, 'text':'另一道题'})) + '\n'
        yield '{"type":"done"}\n'
    gateway.stream_extract = changed
    assert 'event: error' in c.post(f'/api/sessions/{sid}/extract-stream').text
    assert c.get(f'/api/sessions/{sid}').json()['questions'][-1]['id'] == cached['id']


def test_full_extract_reuses_partial_stream_cache(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f'/api/sessions/{sid}/upload', files=[('files', ('q.png', b'\x89PNG\r\n\x1a\nfixture', 'image/png'))])
    async def interrupted(images):
        yield json.dumps(dict(type='question', question=QUESTION)) + '\n'
    gateway.stream_extract = interrupted
    c.post(f'/api/sessions/{sid}/extract-stream')
    before = c.get(f'/api/sessions/{sid}').json()['questions']
    assert c.post(f'/api/sessions/{sid}/analyze').status_code == 200
    assert len(c.get(f'/api/sessions/{sid}').json()['questions']) == len(before)


def test_missing_question_is_client_error_and_hint_mode_removed(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post(f'/api/sessions/{sid}/questions/missing/reveal').status_code == 400
    assert c.patch(f'/api/sessions/{sid}', json={'mode':'hint'}).status_code == 422
