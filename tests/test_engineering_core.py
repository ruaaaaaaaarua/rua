"""Regression contracts for persisted learning facts, not model accuracy."""
import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_api import setup


@pytest.mark.parametrize('kind,solution,answer,correct', [
    ('single', 'B', 'B', True),
    ('single', 'B', 'A', False),
    ('multiple', 'AB', 'B，A', True),
    ('multiple', 'AB', 'A', False),
    ('judge', '正确', '正确', True),
    ('judge', '正确', '错误', False),
])
def test_answer_contract_survives_reload(tmp_path, kind, solution, answer, correct):
    client, app, gateway, sid = setup(tmp_path)
    store, study = app.state.store, app.state.service.study
    session = store.get_session(sid)
    session['questions'][0].update(kind=kind, user_answer='')
    store.save_session(session)

    async def solve(_):
        return {'answer': solution, 'explanation': '固定测试解析'}

    gateway.solve = solve
    assert client.post(f'/api/sessions/{sid}/analyze').status_code == 200
    before = client.get(f'/api/sessions/{sid}').json()['questions'][0]
    assert before['analysis']['correct'] is None
    result = client.post(f'/api/sessions/{sid}/questions/q1/retry', json={'answer': answer})
    assert result.status_code == 200
    attempt = result.json()['questions'][0]['attempts'][-1]
    assert attempt['correct'] is correct and attempt['answer'] == answer
    assert attempt['help_kind'] == 'independent'
    events = study.events(sid, 'q1')
    assert [e['kind'] for e in events] == ['saved', 'answer', 'viewed']
    assert events[1]['correct'] is correct

    # New app/DB connections, not the in-memory session supplied to the service.
    with TestClient(create_app(tmp_path, lambda _: gateway)) as reopened:
        question = reopened.get(f'/api/sessions/{sid}').json()['questions'][0]
        assert question['user_answer'] == ''
        assert question['attempts'] == [attempt]
        learning = reopened.get('/api/wiki/psa-per-unit').json()['learning']
        assert learning['state'] == ('已记录答对' if correct else '近期答错')


@pytest.mark.parametrize('kind,answer', [
    ('single', 'AB'), ('single', 'Z'), ('multiple', 'AA'),
    ('multiple', 'AZ'), ('judge', 'B'),
])
def test_invalid_review_answer_is_atomic_and_run_remains_usable(tmp_path, kind, answer):
    client, app, gateway, sid = setup(tmp_path)
    session = app.state.store.get_session(sid)
    session['questions'][0]['kind'] = kind
    app.state.store.save_session(session)
    valid = '正确' if kind == 'judge' else 'B'

    async def solve(_):
        return {'answer': valid, 'explanation': '测试解析'}

    gateway.solve = solve
    assert client.post(f'/api/sessions/{sid}/analyze').status_code == 200
    study = app.state.service.study
    run = study.start(sid, 'q1')
    before = study.events(sid, 'q1')
    response = client.post(f'/api/reviews/{run["id"]}/answer', json={'answer': answer})
    assert response.status_code == 400
    assert study.events(sid, 'q1') == before
    assert client.post(f'/api/reviews/{run["id"]}/answer', json={'answer': valid}).json()['correct'] is True


def test_review_intervals_cap_and_wrong_answer_resets(tmp_path, monkeypatch):
    import app.study as module
    clock = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz)

    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(module, 'now', lambda: clock.isoformat())
    client, app, _, sid = setup(tmp_path)
    client.post(f'/api/sessions/{sid}/analyze')
    study = app.state.service.study
    for offset, interval in zip((0, 2, 6, 14, 30, 61), (1, 3, 7, 14, 30, 30)):
        clock = datetime(2026, 1, 1, 2, tzinfo=timezone.utc) + timedelta(days=offset)
        result = study.review(study.start(sid, 'q1')['id'], 'B')
        assert result['help_kind'] == 'independent'
        assert datetime.fromisoformat(result['next_due_at']) == clock + timedelta(days=interval)
    clock += timedelta(days=32)
    result = study.review(study.start(sid, 'q1')['id'], 'A')
    assert result['correct'] is False
    assert datetime.fromisoformat(result['next_due_at']) == clock + timedelta(days=1)
    clock += timedelta(days=2)
    result = study.review(study.start(sid, 'q1')['id'], 'B')
    assert datetime.fromisoformat(result['next_due_at']) == clock + timedelta(days=1)


def test_mapping_uniqueness_and_invalid_replacement_preserve_links(tmp_path):
    _, app, _, sid = setup(tmp_path)
    service = app.state.service
    session = app.state.store.get_session(sid)
    question = session['questions'][0]
    service.study.attach(session, question, ['psa-per-unit', 'psa-per-unit'])
    assert len(service.study.links(sid, 'q1')) == 1
    with pytest.raises(ValueError):
        service.study.attach(session, question, ['psa-transformer', 'missing'])
    assert [link['knowledge_id'] for link in service.study.links(sid, 'q1')] == ['psa-per-unit']
    with app.state.store.connect() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO question_links VALUES (?,?,?,?,?)',
                       ('local', sid, 'q1', 'psa-per-unit', 'manual'))


def test_event_primary_key_idempotency_and_not_null_constraints(tmp_path):
    _, app, _, sid = setup(tmp_path)
    study = app.state.service.study
    study.event(sid, 'q1', 'answer', event_id='same', correct=False)
    study.event(sid, 'q1', 'answer', event_id='same', correct=True)
    assert len(study.events(sid, 'q1')) == 1
    assert study.events(sid, 'q1')[0]['correct'] is False
    with app.state.store.connect() as db:
        for valid, data in ((None, '{}'), (1, None)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute('INSERT INTO study_events VALUES (?,?,?,?,?,?)',
                           ('invalid', 'local', sid, 'q1', valid, data))
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('delete_evidence', [False, True])
def test_delete_cleans_projections_and_respects_event_retention(tmp_path, delete_evidence):
    client, app, _, sid = setup(tmp_path)
    client.post(f'/api/sessions/{sid}/analyze')
    run = app.state.service.study.start(sid, 'q1')
    assert client.delete(f'/api/sessions/{sid}?delete_evidence={str(delete_evidence).lower()}').status_code == 200
    assert client.get(f'/api/sessions/{sid}').status_code == 404
    assert client.get('/api/wiki').json()['nodes'] == []
    assert client.get('/api/knowledge').json() == []
    assert client.get('/api/reviews').json()['total'] == 0
    assert not any(m['earned'] for m in client.get('/api/archive').json()['medals'])
    with app.state.store.connect() as db:
        assert db.execute('SELECT count(*) FROM question_links WHERE session_id=?', (sid,)).fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM review_runs WHERE id=?', (run['id'],)).fetchone()[0] == 0
        count = db.execute('SELECT count(*) FROM study_events WHERE session_id=?', (sid,)).fetchone()[0]
        assert count == (0 if delete_evidence else 1)


def test_recommendation_budget_never_reschedules_or_passes_siblings(tmp_path):
    client, app, _, sid = setup(tmp_path)
    session = app.state.store.get_session(sid)
    original = session['questions'][0]
    session['questions'] = [dict(copy.deepcopy(original), id=f'q{i}', text=f'标幺值问题{i}') for i in range(12)]
    app.state.store.save_session(session)
    assert client.post(f'/api/sessions/{sid}/analyze').status_code == 200
    study = app.state.service.study
    before = {f'q{i}': study.events(sid, f'q{i}') for i in range(12)}
    for limit in (3, 5, 10):
        data = client.get(f'/api/reviews?limit={limit}').json()
        assert data['total'] == 12 and len(data['recommended']) == limit
        assert {f'q{i}': study.events(sid, f'q{i}') for i in range(12)} == before
    study.review(study.start(sid, 'q0')['id'], 'B')
    assert {f'q{i}': study.events(sid, f'q{i}') for i in range(1, 12)} == {k: v for k, v in before.items() if k != 'q0'}


def test_api_request_contract_and_local_security_headers(tmp_path):
    client, _, _, sid = setup(tmp_path)
    assert client.post('/api/sessions', json={'unexpected': True}).status_code == 422
    assert client.get('/api/reviews?limit=4').status_code == 422
    response = client.get(f'/api/sessions/{sid}')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert client.get('/api/settings', headers={'host': 'evil.example'}).status_code == 403
    assert client.get('/api/settings', headers={'sec-fetch-site': 'cross-site'}).status_code == 403
    assert client.post('/api/sessions', json={}, headers={'origin': 'http://localhost:9999'}).status_code == 403


def test_legacy_database_initialization_is_additive_and_repeatable(tmp_path):
    # A pre-personal-learning database: no schema rewrite of the original JSON.
    payload = {'id': 'old', 'status': 'ready', 'updated_at': '2020-01-01',
               'questions': [], 'messages': [], 'attachments': [], 'legacy_extra': {'keep': True}}
    with sqlite3.connect(tmp_path / 'learning.sqlite3') as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        db.execute('INSERT INTO sessions VALUES (?,?)', ('old', json.dumps(payload)))
    for _ in range(2):
        app = create_app(tmp_path, lambda _: None)
        assert app.state.store.get_session('old') == payload
        with app.state.store.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {'question_links', 'study_events', 'review_runs', 'archive_profile'} <= tables
