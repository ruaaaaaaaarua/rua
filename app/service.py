"""Learning orchestration; model outputs are proposals, not mutations."""
import base64
import copy
import json
from .store import message, normalized_answer, uid


def public_session(session):
    s=copy.deepcopy(session)
    s.pop('solutions',None)
    for q in s.get('questions',[]):
        q.pop('solution',None)
        a=q.get('analysis') or {}
        if s.get('mode')=='hint' and a.get('correct') is False and not q.get('revealed'):
            hint=a.get('hint') or '请检查题目条件与关键步骤。'
            for key in ('answer','explanation','diagnosis','distinction','knowledge_point'):
                a.pop(key,None)
            a['diagnosis']=hint
    for m in s.get('messages',[]):
        quiz=m.get('quiz')
        if quiz:
            solution=quiz.pop('solution',None) or {}
            if quiz.get('revealed'):
                quiz['correct_answer']=solution.get('answer','')
                quiz['explanation']=solution.get('explanation','')
            quiz.pop('source',None)
            for key in ('answer','explanation','solution','diagnosis','knowledge_point'):
                quiz.get('question',{}).pop(key,None)
                if quiz['status']=='ready' and not quiz.get('revealed'): quiz.pop(key,None)
    return s


class LearningService:
    def __init__(self,store,gateway_factory):
        self.store=store
        self.gateway_factory=gateway_factory

    def gateway(self):
        gateway=self.gateway_factory(self.store.settings())
        gateway.observer=self.store.record_call
        return gateway

    def related(self,question):
        # Bound context to same subject; prioritise exact known names.
        records=self.store.knowledge()
        name=question.get('knowledge','')
        records=[k for k in records if k['name']==name or k['subject']==question.get('subject')]
        records.sort(key=lambda k:k['name']!=name)
        return [{key:k[key] for key in ('id','name','subject','chapter','state','summary','last_verified')} for k in records[:12]]

    def canonicalize(self,q):
        name=q.get('knowledge')
        if not name: return
        matches=[k for k in self.store.knowledge() if k['subject']==q.get('subject') and
                 k['name'].replace(' ','').casefold()==name.replace(' ','').casefold()]
        if matches: q.update(knowledge=matches[0]['name'],chapter=matches[0]['chapter'])

    async def analyze(self,s):
        if s.get('demo'): return s
        if not s['attachments'] and not s['questions']: raise ValueError('请先上传已作答的题目图片。')
        gateway=self.gateway()
        s.update(status='analyzing',error=None); self.store.save_session(s)
        # Each successfully extracted attachment remains cached after failures.
        for a in s['attachments']:
            if a.get('reference') or a.get('extracted') or a.get('deleted'): continue
            blob=(self.store.attachments/a['id']).read_bytes()
            data='data:'+a['mime']+';base64,'+base64.b64encode(blob).decode()
            extracted=await gateway.extract([dict(data_url=data,name=a['name'])])
            for q in extracted:
                q.update(id=uid(),attachment_id=a['id'],revealed=False)
                self.canonicalize(q)
                s['questions'].append(q)
            a['extracted']=True
            self.store.save_session(s)
        failures=[]
        for q in s['questions']:
            if q.get('analysis',{}).get('status')=='confirmed': continue
            try:
                solution=await gateway.solve(q)
                diagnosis=await gateway.diagnose({**q,'reference_material':s.get('references',[])[-5:]},solution,self.related(q))
                answer=solution.get('answer','')
                valid=solution.get('valid',True) and solution.get('status','confirmed')!='pending' and diagnosis.get('status','confirmed')!='pending' and bool(answer)
                supplied=bool(str(q.get('user_answer') or '').strip())
                correct=normalized_answer(q.get('user_answer'),q['kind'])==normalized_answer(answer,q['kind']) if valid and supplied else None
                q['analysis']={**diagnosis,'answer':answer,'explanation':solution.get('explanation',''),
                    'correct':correct,'status':'confirmed' if valid and supplied else 'pending','source':'ai'}
                q['solution']=solution
                self.store.record_evidence(s['id'],q)
            except Exception as e:
                from .providers import ProviderError
                if not isinstance(e,ProviderError): raise
                failures.append(str(q.get('number','')))
                q['analysis']=dict(correct=None,status='pending',source='ai',diagnosis=str(e),knowledge_point='',hint='请核对题目信息后重试。')
            self.store.save_session(s)
        s.update(status='error' if failures else 'ready',error='部分题目未能完成分析，可重试：'+ '、'.join(failures) if failures else None)
        if not any(m['type']=='overview' for m in s['messages']):
            s['messages'].append(message('assistant','已完成整页分析。先看总览，再选择想讨论的题目。','overview'))
        if s['title']=='新的刷题' and s['questions']:
            s['title']=(s['questions'][0].get('subject') or '整页刷题')+' · '+str(len(s['questions']))+' 题'
        self.store.save_session(s)
        return s

    def question(self,s,qid):
        for q in s['questions']:
            if q['id']==qid:return q
        raise ValueError('没有找到这道题。')

    async def chat(self,s,text,qid=None):
        if s.get('demo'):
            s['messages'].extend([message('user',text),message('assistant','这是交互演示，不会调用模型或更新真实知识状态。配置模型后，新建对话上传自己的题目即可开始。')])
            self.store.save_session(s); return s
        q=self.question(s,qid) if qid else None
        s['messages'].append(message('user',text)); s.update(status='chatting',error=None); self.store.save_session(s)
        visible=public_session(s)
        context=dict(questions=[x for x in visible['questions'] if x['id']==qid] if q else visible['questions'],
            history=visible['messages'][-12:],knowledge=self.related(q) if q else [],
            references=s.get('references',[])[-5:])
        response=await self.gateway().chat(context,text,s['mode'])
        action=response.get('action') or {}
        action_type=action.get('type','none')
        target=action.get('question_id') or qid
        if action_type=='train':
            return await self.train(s,target,action.get('knowledge_id'),action.get('purpose') or 'variant')
        if action_type=='recheck':
            return await self.recheck(s,target,action.get('reference') or text)
        if action_type=='answer_quiz':
            return await self.answer_quiz(s,action.get('quiz_id'),action.get('answer',''),action.get('reasoning') or '')
        if action_type=='retry_question':
            return await self.retry_question(s,target,action.get('answer',''),action.get('reasoning') or '')
        if action_type in ('reveal','navigate'):
            selected=self.question(s,target)
            s['selected_question_id']=selected['id']
            if action_type=='reveal': selected.update(revealed=True,help_seen=True)
            s['messages'].append(message('assistant','已打开第 '+str(selected['number'])+' 题。'+('答案与解析已展开。' if action_type=='reveal' else '')))
        else:
            s['messages'].append(message('assistant',response['content']))
            for item in ([q] if q else s['questions']): item['help_seen']=True
            for m in s['messages']:
                quiz=m.get('quiz')
                if quiz and quiz['status']=='ready': quiz['help_kind']='assisted'
        s.update(status='ready',error=None); self.store.save_session(s); return s

    async def train(self,s,qid=None,kid=None,purpose='variant'):
        if s.get('demo'): raise ValueError('演示只展示预设训练；请配置模型后在真实对话中生成。')
        q=self.question(s,qid) if qid else None
        k=next((x for x in self.store.knowledge() if x['id']==kid),None) if kid else None
        if not q and not k: raise ValueError('请先选择题目或知识点。')
        s.update(status='training',error=None); self.store.save_session(s)
        context={'question':q,'knowledge':k or (self.related(q) if q else []),'references':s.get('references',[])[-5:]}
        gateway=self.gateway()
        for _ in range(2):
            generated=await gateway.generate(context,purpose)
            checked=await gateway.verify(generated)
            kind=generated.get('kind','single')
            agrees=normalized_answer(generated.get('answer'),kind)==normalized_answer(checked.get('answer'),kind)
            if kind=='short' and checked.get('valid'):
                comparison=await gateway.diagnose({**generated,'user_answer':generated.get('answer'),'reasoning':''},checked,[])
                agrees=comparison.get('correct') is True and comparison.get('status')=='confirmed'
            if checked.get('valid') and not checked.get('issues') and agrees:
                if not generated.get('answer'):continue
                source=dict(question_id=qid,knowledge_id=kid,subject=(q or k or {}).get('subject','未分类'),
                    chapter=(q or k or {}).get('chapter','未分类'),knowledge=(q or {}).get('knowledge') or (k or {}).get('name','未分类'))
                if purpose=='prerequisite':
                    source.update(subject=generated.get('subject') or source['subject'],chapter=generated.get('chapter') or source['chapter'],
                        knowledge=generated.get('knowledge') or source['knowledge'])
                helped=bool(q and (q.get('help_seen') or q.get('analysis') or q.get('revealed')))
                # A just-discussed concept is not an independent delayed retest.
                if k and any(e.get('session_id')==s['id'] for e in k.get('evidence',[])): helped=True
                quiz=dict(id=uid(),purpose=purpose,question=generated,status='ready',solution=checked,
                    source=source,help_kind='assisted' if helped else 'independent')
                s['messages'].append(message('assistant','只验证当前这个点。答完后由你决定是否继续。','quiz',quiz=quiz))
                s.update(status='ready',error=None); self.store.save_session(s); return s
        raise ValueError('这次生成的题目未通过独立复核，已停止。没有计入学习记录，可以稍后重试。')

    async def answer_quiz(self,s,quizid,answer,reasoning=''):
        quiz=next((m['quiz'] for m in s['messages'] if m.get('quiz',{}).get('id')==quizid),None)
        if not quiz:raise ValueError('没有找到验证题。')
        if quiz.get('disputed'):raise ValueError('这道验证题的依据已经失效，请重新发起复核或训练。')
        if quiz['status']!='ready':raise ValueError('这道验证题已经作答；如需再测，请主动发起新题。')
        q=quiz['question']; correct=normalized_answer(answer,q['kind'])==normalized_answer(quiz['solution']['answer'],q['kind'])
        diagnosis=dict(reasoning_ok=None,diagnosis='',error_type='unknown',knowledge_point='本次验证通过。' if correct else '本次验证未通过，具体原因待确认。')
        if (reasoning or q['kind']=='short') and not s.get('demo'):
            diagnosis=await self.gateway().diagnose({**q,'user_answer':answer,'reasoning':reasoning},quiz['solution'],[])
        if q['kind']=='short': correct=diagnosis.get('correct')
        if diagnosis.get('status')=='pending': correct=None
        if correct is None: raise ValueError('暂时无法可靠判断这次回答，请补充一句理由再试。')
        quiz.update(status='answered',answer=answer,correct=correct,reasoning=reasoning,
            feedback=('✅ 正确。' if diagnosis.get('reasoning_ok') is not False else '选项正确，思路需注意：'+diagnosis.get('diagnosis','')) if correct else
            ('请再检查关键条件。可查看解析，或继续追问。' if s['mode']=='hint' else '应答 '+quiz['solution']['answer']+'。'+quiz['solution'].get('explanation','')[:160]))
        evidence_q={**q,**quiz['source'],'id':quizid,'reasoning':reasoning,'confidence':'unknown',
            'analysis':{**diagnosis,'correct':correct,'status':'confirmed'}}
        self.store.record_evidence(s['id'],evidence_q,attempt_id=quizid,help_kind=quiz['help_kind'],purpose=quiz['purpose'])
        s.update(status='ready',error=None);self.store.save_session(s);return s

    async def recheck(self,s,qid,text):
        if s.get('demo'):raise ValueError('演示记录不进行模型复核。')
        q=self.question(s,qid)
        # Disputed judgments are immediately suspended until recheck succeeds.
        self.store.retract(s['id'],qid)
        for attempt in q.get('attempts',[]):
            self.store.retract(s['id'],attempt['id']);attempt['disputed']=True
        for m in s['messages']:
            if m.get('quiz',{}).get('source',{}).get('question_id')==qid:
                self.store.retract(s['id'],m['quiz']['id'])
                m['quiz']['disputed']=True
        q['analysis']={'status':'pending','correct':None,'diagnosis':'正在核查用户补充的资料。'}
        q.pop('solution',None)
        s['messages'].append(message('user','复核第 '+str(q['number'])+' 题：'+text))
        s.update(status='analyzing',error=None);self.store.save_session(s)
        reference_note=json.dumps({'user_note':text,'saved_references':s.get('references',[])[-5:]},ensure_ascii=False)
        solution=await self.gateway().solve({**q,'reference_note':reference_note})
        diagnosis=await self.gateway().diagnose(q,solution,self.related(q))
        valid=solution.get('valid',True) and solution.get('status','confirmed')!='pending' and diagnosis.get('status','confirmed')!='pending' and bool(solution.get('answer'))
        q['solution']=solution
        q['analysis']={**diagnosis,'answer':solution.get('answer',''),'explanation':solution.get('explanation',''),
            'correct': normalized_answer(q['user_answer'],q['kind'])==normalized_answer(solution.get('answer'),q['kind']) if valid else None,
            'status':'confirmed' if valid else 'pending','source':'ai_rechecked'}
        self.store.record_evidence(s['id'],q)
        s['messages'].append(message('assistant','已重新核查并更新本题记录；原判断及依赖它的验证证据已撤回。'+ ('仍有疑点，暂不更新知识判断。' if not valid else '')))
        s.update(status='ready',error=None);self.store.save_session(s);return s

    async def recheck_quiz(self,s,quizid,text):
        quiz=next((m['quiz'] for m in s['messages'] if m.get('quiz',{}).get('id')==quizid),None)
        if not quiz: raise ValueError('验证题不存在。')
        if s.get('demo'): raise ValueError('演示题不进行实时复核。')
        self.store.retract(s['id'],quizid)
        quiz['disputed']=True
        s.update(status='analyzing',error=None);self.store.save_session(s)
        reference_note=json.dumps({'user_note':text,'saved_references':s.get('references',[])[-5:]},ensure_ascii=False)
        checked=await self.gateway().solve({**quiz['question'],'reference_note':reference_note})
        valid=checked.get('valid') and checked.get('status','confirmed')=='confirmed'
        if valid:
            quiz['solution']=checked
            quiz['disputed']=False
            if quiz['status']=='answered':
                answer=quiz['answer'];reasoning=quiz.get('reasoning','')
                quiz['status']='ready'
                await self.answer_quiz(s,quizid,answer,reasoning)
        s['messages'].append(message('assistant','验证题已重新核查，相关记录已更新。' if valid else '验证题仍有疑点，已暂停其学习证据。'))
        s.update(status='ready',error=None);self.store.save_session(s);return s

    async def retry_question(self,s,qid,answer,reasoning=''):
        q=self.question(s,qid)
        solution=q.get('solution') or q.get('analysis') or {}
        if not solution.get('answer') or q.get('analysis',{}).get('status')!='confirmed':
            raise ValueError('这道题的答案尚未确认，请先完成分析或复核。')
        correct=normalized_answer(answer,q['kind'])==normalized_answer(solution['answer'],q['kind'])
        diagnosis=dict(reasoning_ok=None,diagnosis='',knowledge_point='本次重答记录。')
        if reasoning and not s.get('demo'):
            diagnosis=await self.gateway().diagnose({**q,'user_answer':answer,'reasoning':reasoning},solution,self.related(q))
        if diagnosis.get('status')=='pending':
            raise ValueError('这次思路暂时无法可靠判断，请补充信息后再确认；未更新知识状态。')
        attempt=dict(id=uid(),answer=answer,reasoning=reasoning,correct=correct,help_kind='assisted')
        q.setdefault('attempts',[]).append(attempt)
        evidence_q={**q,'id':attempt['id'],'reasoning':reasoning,
            'analysis':{**diagnosis,'correct':correct,'status':'confirmed'}}
        self.store.record_evidence(s['id'],evidence_q,help_kind='assisted',purpose='retry')
        s['messages'].append(message('user','第 '+str(q['number'])+' 题重答：'+answer+('；'+reasoning if reasoning else '')))
        s['messages'].append(message('assistant','✅ 这次答对了。首答与提示后重答已分别记录。' if correct else '这次仍未答对。可以继续追问具体卡点，或查看答案。'))
        s.update(status='ready',error=None);self.store.save_session(s);return s
