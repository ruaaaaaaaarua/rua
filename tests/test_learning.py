import pytest
from app.store import Store, normalized_answer
from app.service import public_session


def test_multiselect_order_and_judgement():
    assert normalized_answer('CA', 'multiple') == normalized_answer('A,C', 'multiple')
    assert normalized_answer('√', 'judge') == normalized_answer('正确', 'judge')
    assert normalized_answer('A', 'single') != normalized_answer('B', 'single')


def test_pending_never_creates_knowledge(tmp_path):
    store = Store(tmp_path)
    s = store.create_session()
    q = {'id':'q1','subject':'电路','chapter':'基础','knowledge':'公式适用条件',
         'analysis':{'status':'pending','correct':None,'diagnosis':'不确定'},'confidence':'unknown'}
    store.record_evidence(s['id'], q)
    assert store.knowledge() == []


def test_correction_retracts_and_delete_preserves_summary(tmp_path):
    store = Store(tmp_path)
    s = store.create_session()
    q = {'id':'q1','subject':'电路','chapter':'基础','knowledge':'公式适用条件','reasoning':'公式',
         'confidence':'certain','analysis':{'status':'confirmed','correct':False,'diagnosis':'条件混淆','reasoning_ok':False}}
    store.record_evidence(s['id'], q)
    assert store.knowledge()[0]['state'] == '待验证'
    q['analysis'].update(correct=True, reasoning_ok=True,diagnosis='')
    store.record_evidence(s['id'], q)
    k = store.knowledge()[0]
    assert k['evidence_count'] == 1
    assert k['state'] != '表现较稳定'
    store.delete_session(s['id'], False)
    assert store.knowledge()[0]['evidence'][0]['source_deleted'] is True
    assert store.get_session(s['id']) is None


def test_delete_evidence_removes_projection(tmp_path):
    store=Store(tmp_path); s=store.create_session()
    q={'id':'q','knowledge':'K','analysis':{'status':'confirmed','correct':False}}
    store.record_evidence(s['id'],q)
    store.delete_session(s['id'],True)
    assert not store.knowledge()


def test_demo_does_not_pollute_knowledge(tmp_path):
    store=Store(tmp_path); s=store.create_session(demo=True)
    store.record_evidence(s['id'],{'id':'q','knowledge':'K','analysis':{'status':'confirmed','correct':False}})
    assert not store.knowledge()


def test_hint_redacts_answers_and_unanswered_quiz():
    session={'mode':'hint','questions':[{'id':'q','revealed':False,'analysis':{
        'correct':False,'answer':'B','explanation':'B is correct','diagnosis':'选择 B','hint':'检查单位','distinction':'B'}}],
        'messages':[{'type':'quiz','quiz':{'id':'x','status':'ready','question':{'text':'t','answer':'C','explanation':'C'},'answer':'C','solution':{'answer':'C'}}}]}
    public=public_session(session)
    assert 'answer' not in public['questions'][0]['analysis']
    assert 'B' not in str(public['questions'][0]['analysis'])
    assert 'answer' not in public['messages'][0]['quiz']
    assert 'answer' not in public['messages'][0]['quiz']['question']
    assert session['questions'][0]['analysis']['answer']=='B'


def test_call_log_keeps_usage_without_secrets(tmp_path):
    store=Store(tmp_path)
    store.record_call(dict(task='solve',profile_id='p',model='m',success=True,input_tokens=10,output_tokens=5,duration_ms=8,api_key='SECRET',prompt='PRIVATE'))
    with store.connect() as db:
        row=db.execute('SELECT data FROM calls').fetchone()
    assert 'SECRET' not in row['data'] and 'PRIVATE' not in row['data']
    assert 'input_tokens' in row['data']
