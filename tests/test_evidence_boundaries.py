import asyncio
import json
from app.store import Store
from app.service import LearningService,public_session
from app.providers import ProviderError
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


def test_call_record_omits_sensitive_error_details(tmp_path):
    store = Store(tmp_path)
    store.record_call({
        'task': 'solve', 'profile_id': 'profile', 'model': 'model',
        'success': False, 'error_kind': 'response_schema',
        'prompt': 'private prompt', 'api_key': 'private key', 'raw_response': 'private response',
    })

    with store.connect() as db:
        event = json.loads(db.execute('SELECT data FROM calls').fetchone()['data'])
    assert event['error_kind'] == 'response_schema'
    assert 'prompt' not in event and 'api_key' not in event and 'raw_response' not in event


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


def _two_answered_questions():
    base=asyncio.run(Gateway().extract([]))[0]
    return [{**base,'id':'q1'}, {**base,'id':'q2','user_answer':'B'}]


def test_batched_analysis_avoids_per_question_calls(tmp_path):
    class Batched(Gateway):
        solves=0
        diagnose_items=[]
        async def solve(self,q):
            Batched.solves+=1; return await Gateway.solve(self,q)
        async def solve_batch(self,questions):
            return [dict(index=i,answer='B',explanation='平方关系',valid=True,status='confirmed') for i in range(len(questions))]
        async def diagnose_batch(self,items):
            type(self).diagnose_items=items
            return [dict(index=it['index'],reasoning_ok=False,diagnosis='忽略平方',knowledge_point='功率与电压平方成正比',distinction='',hint='检查指数',error_type='formula_error',status='confirmed') for it in items]
    store=Store(tmp_path);s=store.create_session();s['questions']=_two_answered_questions();store.save_session(s)
    gw=Batched()
    service=LearningService(store,lambda _:gw)
    service.related=lambda question:[{'id':str(index)} for index in range(4)]
    result=asyncio.run(service.analyze(s))
    assert Batched.solves==0
    assert [q['analysis']['correct'] for q in result['questions']]==[False,True]
    assert all(q['analysis']['status']=='confirmed' for q in result['questions'])
    assert store.knowledge()[0]['evidence_count']==2
    assert all(len(item['history'])==3 for item in Batched.diagnose_items)


def test_batch_partial_results_fall_back_per_question(tmp_path):
    class Partial(Gateway):
        solves=0
        async def solve_batch(self,questions):
            return [dict(index=0,answer='B',explanation='平方关系',valid=True,status='confirmed')]
        async def diagnose_batch(self,items):
            return [dict(index=0,reasoning_ok=None,diagnosis='',knowledge_point='平方关系',distinction='',hint='检查指数',status='confirmed')]
        async def solve(self,q):
            Partial.solves+=1; return dict(answer='B',explanation='平方关系',valid=True)
    store=Store(tmp_path);s=store.create_session();s['questions']=_two_answered_questions();store.save_session(s)
    gw=Partial()
    result=asyncio.run(LearningService(store,lambda _:gw).analyze(s))
    assert Partial.solves==1
    assert all(q['analysis']['status']=='confirmed' for q in result['questions'])


def test_batch_diagnosis_failure_reuses_batch_solutions(tmp_path):
    class DiagnosisFails(Gateway):
        batch_diagnoses=single_solves=single_diagnoses=0
        async def solve_batch(self,questions):
            return [dict(index=i,answer='B',explanation='平方关系',valid=True,status='confirmed') for i in range(len(questions))]
        async def diagnose_batch(self,items):
            type(self).batch_diagnoses+=1
            raise ProviderError('批量诊断暂时不可用')
        async def solve(self,q):
            type(self).single_solves+=1
            return await super().solve(q)
        async def diagnose(self,*args):
            type(self).single_diagnoses+=1
            return await super().diagnose(*args)

    store=Store(tmp_path);s=store.create_session();s['questions']=_two_answered_questions();store.save_session(s)
    gateway=DiagnosisFails()
    result=asyncio.run(LearningService(store,lambda _:gateway).analyze(s))
    assert DiagnosisFails.single_solves==0
    assert DiagnosisFails.batch_diagnoses==2
    assert DiagnosisFails.single_diagnoses==2
    assert all(q['analysis']['status']=='confirmed' for q in result['questions'])


def test_extract_persists_questions_without_analysis_or_evidence(tmp_path):
    class VisionOnly(Gateway):
        extracts=solves=diagnoses=0
        async def extract(self,images):
            type(self).extracts+=1
            return await Gateway.extract(self,images)
        async def solve(self,question):
            type(self).solves+=1
            return await Gateway.solve(self,question)
        async def diagnose(self,question,solution,history):
            type(self).diagnoses+=1
            return await Gateway.diagnose(self,question,solution,history)

    store=Store(tmp_path);session=store.create_session()
    store.attachments.joinpath('image').write_bytes(b'png')
    session['attachments']=[dict(id='image',name='page.png',mime='image/png',extracted=False)]
    store.save_session(session)

    result=asyncio.run(LearningService(store,lambda _:VisionOnly()).extract(session))

    assert result['status']=='extracted'
    assert result['attachments'][0]['extracted'] is True
    assert result['questions'] and 'analysis' not in result['questions'][0]
    assert (VisionOnly.extracts,VisionOnly.solves,VisionOnly.diagnoses)==(1,0,0)
    assert store.knowledge()==[]


def test_stream_extract_persists_each_valid_question_before_done(tmp_path):
    first=asyncio.run(Gateway().extract([]))[0]
    second={**first,'number':'2','text':'第二题'}

    class Streaming(Gateway):
        async def stream_extract(self,images):
            yield json.dumps({'type':'question','question':first},ensure_ascii=False)+'\n'
            yield json.dumps({'type':'question','question':second},ensure_ascii=False)+'\n'
            yield '{"type":"done"}\n'

    store=Store(tmp_path);session=store.create_session()
    store.attachments.joinpath('image').write_bytes(b'png')
    session['attachments']=[dict(id='image',name='page.png',mime='image/png',extracted=False)]
    store.save_session(session)

    events=asyncio.run(_collect(LearningService(store,lambda _:Streaming()).extract_stream(session)))

    assert [event['type'] for event in events]==['question','question','done']
    assert len(session['questions'])==2
    assert all('analysis' not in question for question in session['questions'])
    assert session['status']=='extracted'
    assert store.knowledge()==[]


def test_stream_extract_accepts_a_final_ndjson_line_without_newline(tmp_path):
    question=asyncio.run(Gateway().extract([]))[0]

    class Streaming(Gateway):
        async def stream_extract(self,images):
            yield json.dumps({'type':'question','question':question},ensure_ascii=False)+'\n'
            yield '{"type":"done"}'

    store=Store(tmp_path);session=store.create_session()
    store.attachments.joinpath('image').write_bytes(b'png')
    session['attachments']=[dict(id='image',name='page.png',mime='image/png',extracted=False)]
    store.save_session(session)

    events=asyncio.run(_collect(LearningService(store,lambda _:Streaming()).extract_stream(session)))

    assert [event['type'] for event in events]==['question','done']
    assert session['status']=='extracted'


async def _collect(events):
    return [event async for event in events]
