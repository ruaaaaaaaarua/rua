import asyncio
from app.store import Store
from app.service import LearningService,public_session
from tests.test_api import Gateway


def test_pending_diagnosis_does_not_become_confirmed(tmp_path):
    class Pending(Gateway):
        async def diagnose(self,*args):
            return dict(status='pending',correct=None,diagnosis='题目条件存在歧义',reasoning_ok=None)
    store=Store(tmp_path); s=store.create_session()
    s['questions']=asyncio.run(Gateway().extract([]));s['questions'][0]['id']='q'
    store.save_session(s)
    service=LearningService(store,lambda _:Pending())
    result=asyncio.run(service.analyze(s))
    assert result['questions'][0]['analysis']['correct'] is None
    assert not store.knowledge()


def test_disputed_quiz_cannot_update_knowledge(tmp_path):
    store=Store(tmp_path);s=store.create_session()
    s['messages']=[{'quiz':{'id':'quiz','disputed':True,'status':'ready','question':{'kind':'single'},'solution':{'answer':'B'}}}]
    store.save_session(s)
    service=LearningService(store,lambda _:Gateway())
    import pytest
    with pytest.raises(ValueError,match='失效|复核|争议'):
        asyncio.run(service.answer_quiz(s,'quiz','B'))
    assert not store.knowledge()


def test_revealed_quiz_answer_is_not_available_until_explicit_action():
    s={'mode':'hint','questions':[],'messages':[{'quiz':{'id':'q','status':'answered','question':{'kind':'single','answer':'B','explanation':'B'},'solution':{'answer':'B','explanation':'平方'},'answer':'A','correct':False}}]}
    p=public_session(s)
    assert 'explanation' not in p['messages'][0]['quiz']
    s['messages'][0]['quiz']['revealed']=True
    p=public_session(s)
    assert p['messages'][0]['quiz']['correct_answer']=='B'
    assert p['messages'][0]['quiz']['explanation']=='平方'


def test_original_retry_keeps_first_evidence_and_is_assisted(tmp_path):
    store=Store(tmp_path); s=store.create_session()
    q=asyncio.run(Gateway().extract([]))[0];q['id']='q';s['questions']=[q];store.save_session(s)
    svc=LearningService(store,lambda _:Gateway())
    asyncio.run(svc.analyze(s))
    result=asyncio.run(svc.retry_question(s,'q','B',''))
    k=store.knowledge()[0]
    assert k['evidence_count']==2
    assert any(e['correct'] is False for e in k['evidence'])
    assert k['evidence'][0]['help_kind']=='assisted'
    assert result['questions'][0]['user_answer']=='A'
    assert result['questions'][0]['attempts'][-1]['answer']=='B'


def test_recheck_replaces_solution_for_future_retry(tmp_path):
    class Revised(Gateway):
        async def solve(self,q): return dict(answer='C',explanation='新核查结果',valid=True)
        async def diagnose(self,*args): return dict(status='confirmed',reasoning_ok=None)
    store=Store(tmp_path); s=store.create_session()
    q=asyncio.run(Gateway().extract([]))[0]; q['id']='q'; s['questions']=[q]; store.save_session(s)
    svc=LearningService(store,lambda _:Gateway()); asyncio.run(svc.analyze(s))
    svc.gateway_factory=lambda _:Revised()
    asyncio.run(svc.recheck(s,'q','补充完整条件'))
    result=asyncio.run(svc.retry_question(s,'q','C'))
    assert result['questions'][0]['attempts'][-1]['correct'] is True


def test_chat_sanitizes_quiz_history_and_marks_help(tmp_path):
    class Inspect(Gateway):
        async def chat(self,context,text,mode):
            quiz=context['history'][0]['quiz']
            assert 'solution' not in quiz
            assert 'answer' not in quiz['question']
            assert 'knowledge_point' not in quiz['question']
            return {'content':'检查指数。'}
    store=Store(tmp_path);s=store.create_session(mode='hint')
    s['messages']=[{'id':'m','type':'quiz','role':'assistant','quiz':{'id':'quiz','status':'ready',
        'help_kind':'independent','question':{'kind':'single','text':'Q','answer':'B','knowledge_point':'B is correct'},
        'solution':{'answer':'B'}}}]
    store.save_session(s)
    asyncio.run(LearningService(store,lambda _:Inspect()).chat(s,'给个提示'))
    assert s['messages'][0]['quiz']['help_kind']=='assisted'


def test_explicit_chat_action_generates_one_quiz(tmp_path):
    class Action(Gateway):
        async def chat(self,*args):return {'content':'开始验证。','action':{'type':'train','question_id':'q','purpose':'variant'}}
    store=Store(tmp_path);s=store.create_session()
    s['questions']=[{**asyncio.run(Gateway().extract([]))[0],'id':'q'}];store.save_session(s)
    asyncio.run(LearningService(store,lambda _:Action()).chat(s,'第1题来一道类似题'))
    assert len([m for m in s['messages'] if m.get('quiz')])==1


def test_prerequisite_evidence_targets_generated_knowledge(tmp_path):
    class Prerequisite(Gateway):
        async def generate(self,context,purpose):
            return {**await super().generate(context,purpose),'knowledge':'平方运算','subject':'数学基础','chapter':'代数'}
    store=Store(tmp_path);s=store.create_session()
    s['questions']=[{**asyncio.run(Gateway().extract([]))[0],'id':'q'}];store.save_session(s)
    svc=LearningService(store,lambda _:Prerequisite())
    asyncio.run(svc.train(s,'q',purpose='prerequisite'))
    quiz=s['messages'][-1]['quiz']
    asyncio.run(svc.answer_quiz(s,quiz['id'],'B'))
    assert store.knowledge()[0]['name']=='平方运算'


def test_short_verification_accepts_semantically_equivalent_answers(tmp_path):
    class Short(Gateway):
        async def generate(self,*args):return dict(kind='short',text='功率如何变化？',options=[],answer='增大',explanation='关系成立')
        async def verify(self,*args):return dict(answer='变大',explanation='关系成立',valid=True)
        async def diagnose(self,*args):return dict(correct=True,status='confirmed',reasoning_ok=None)
    store=Store(tmp_path);s=store.create_session()
    s['questions']=[{**asyncio.run(Gateway().extract([]))[0],'id':'q'}];store.save_session(s)
    result=asyncio.run(LearningService(store,lambda _:Short()).train(s,'q'))
    assert result['messages'][-1]['quiz']['status']=='ready'


def test_knowledge_summary_retains_understanding_evidence_after_delete(tmp_path):
    store=Store(tmp_path);s=store.create_session()
    q=dict(id='q',knowledge='概念',reasoning='有明确依据',analysis=dict(correct=True,status='confirmed',reasoning_ok=True))
    store.record_evidence(s['id'],q)
    before=store.knowledge()[0]['state']
    store.delete_session(s['id'])
    assert store.knowledge()[0]['state']==before


def test_pending_retry_does_not_add_evidence(tmp_path):
    class Pending(Gateway):
        async def diagnose(self,*args):return dict(status='pending',correct=None,reasoning_ok=None)
    store=Store(tmp_path);s=store.create_session()
    s['questions']=[{**asyncio.run(Gateway().extract([]))[0],'id':'q'}];store.save_session(s)
    svc=LearningService(store,lambda _:Gateway());asyncio.run(svc.analyze(s))
    svc.gateway_factory=lambda _:Pending()
    import pytest
    with pytest.raises(ValueError,match='确认|判断'):
        asyncio.run(svc.retry_question(s,'q','B','有争议的思路'))
    assert store.knowledge()[0]['evidence_count']==1


def test_saved_reference_is_used_in_recheck(tmp_path):
    class Reference(Gateway):
        async def solve(self,q):
            assert '参考页中的附加条件' in q['reference_note']
            return await super().solve(q)
    store=Store(tmp_path);s=store.create_session()
    s['questions']=[{**asyncio.run(Gateway().extract([]))[0],'id':'q'}]
    s['references']=[{'text':'参考页中的附加条件'}];store.save_session(s)
    asyncio.run(LearningService(store,lambda _:Reference()).recheck(s,'q','按刚上传的资料核查'))
