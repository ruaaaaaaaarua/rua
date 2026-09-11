"""Local HTTP boundary; private data never needs a remote application server."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .store import Store, TASKS, message, uid
from .service import LearningService, public_session
from .demo import create_demo

ROOT=Path(__file__).resolve().parent.parent

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class SessionInput(Input):
    title: str=Field(default='新的刷题',max_length=100)
    mode: Optional[Literal['direct','hint']]=None

class SessionPatch(Input):
    title: Optional[str]=Field(default=None,max_length=100)
    mode: Optional[Literal['direct','hint']]=None

class Text(Input):
    text: str=Field(min_length=1,max_length=30000)
    question_id: Optional[str]=None

class Option(Input):
    key:str=Field(min_length=1,max_length=8)
    text:str=Field(max_length=8000)

class QuestionPatch(Input):
    text:Optional[str]=Field(default=None,min_length=1,max_length=20000)
    options:Optional[List[Option]]=None
    user_answer:Optional[str]=Field(default=None,max_length=200)
    reasoning:Optional[str]=Field(default=None,max_length=10000)
    confidence:Optional[Literal['certain','unsure','guess','unknown']]=None
    kind:Optional[Literal['single','multiple','judge']]=None

class Train(Input):
    question_id:Optional[str]=None
    knowledge_id:Optional[str]=None
    purpose:Literal['variant','verify','prerequisite','depth']='variant'

class Answer(Input):
    answer:str=Field(min_length=1,max_length=200)
    reasoning:str=Field(default='',max_length=10000)

class Profile(Input):
    id:str=Field(default='',max_length=100)
    name:str=Field(min_length=1,max_length=100)
    base_url:str=Field(min_length=1,max_length=1000)
    model:str=Field(min_length=1,max_length=200)
    api_key:Optional[str]=Field(default=None,max_length=4096)
    has_key:Optional[bool]=None
    remove_key:bool=False
    disable_thinking:bool=False

    @field_validator('base_url')
    @classmethod
    def valid_url(cls,value):
        url=urlparse(value)
        if url.scheme not in ('https','http') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('使用不含凭据和查询参数的 HTTP(S) 接口地址')
        if url.scheme=='http' and url.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('远程接口请使用 HTTPS，本地模型可用 HTTP')
        return value.rstrip('/')

class Settings(Input):
    profiles:List[Profile]=Field(max_length=20)
    tasks:Dict[str,str]
    mode:Literal['direct','hint']='direct'
    rate_tpm:Optional[int]=Field(default=None,ge=1000,le=10000000)

    @field_validator('tasks')
    @classmethod
    def task_names(cls,v):
        if set(v)!=set(TASKS):raise ValueError('需要配置 vision/solve/chat/generate/verify 五个任务')
        return v

class TestProfile(Input):
    profile_id:str


def create_app(data_dir=None,gateway_factory=None):
    store=Store(data_dir or os.environ.get('GRID_LEARNING_DATA',ROOT/'data'))
    if gateway_factory is None:
        from .providers import ModelGateway
        gateway_factory=ModelGateway
    service=LearningService(store,gateway_factory)
    app=FastAPI(title='电网学习助手',docs_url='/api/docs',openapi_url='/api/openapi.json')
    app.state.store=store;app.state.service=service
    locks={}

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request,exc):
        fields=['.'.join(str(p) for p in e['loc'][1:]) for e in exc.errors()]
        return JSONResponse({'detail':'输入格式不正确，请检查：'+'、'.join(fields)},status_code=422)

    @app.middleware('http')
    async def local_guard(request,call_next):
        # Reject DNS rebinding and cross-site writes to this local credential-bearing app.
        if request.url.hostname not in ('localhost','127.0.0.1','::1','testserver'):
            return JSONResponse({'detail':'仅允许本机访问'},status_code=403)
        origin=request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin:
            parsed=urlparse(origin)
            if parsed.hostname not in ('localhost','127.0.0.1','::1','testserver') or parsed.port not in (None,8765,5173):
                return JSONResponse({'detail':'拒绝跨站请求'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'拒绝跨站请求'},status_code=403)
        response=await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        return response

    def get(sid):
        s=store.get_session(sid)
        if not s:raise HTTPException(404,'没有找到这次刷题')
        return s

    @asynccontextmanager
    async def locked(sid):
        lock=locks.setdefault(sid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'当前对话正在处理，请等待完成。')
        async with lock:yield get(sid)

    async def operation(sid,fn):
        async with locked(sid) as s:
            try:return public_session(await fn(s))
            except (ValueError,) as e:
                s.update(status='error',error=str(e));store.save_session(s)
                raise HTTPException(400,str(e))
            except Exception as e:
                from .providers import ProviderError
                safe=str(e) if isinstance(e,ProviderError) else '处理未完成，记录已保存。请检查模型配置后重试。'
                s.update(status='error',error=safe);store.save_session(s)
                raise HTTPException(502,safe)

    @app.get('/api/health')
    def health():return {'ok':True}

    @app.get('/api/sessions')
    def sessions():return store.sessions()

    @app.post('/api/sessions')
    def new_session(body:SessionInput):return public_session(store.create_session(body.title,body.mode))

    @app.get('/api/sessions/{sid}')
    def session(sid:str):return public_session(get(sid))

    @app.patch('/api/sessions/{sid}')
    async def update_session(sid:str,body:SessionPatch):
        async with locked(sid) as s:
            if body.mode:
                if s['mode']=='direct' or body.mode=='direct':
                    for q in s['questions']:
                        if q.get('analysis',{}).get('status')=='confirmed':
                            q.update(revealed=True,help_seen=True)
                preferences=store.settings();preferences['mode']=body.mode;store.save_settings(preferences)
            s.update(body.model_dump(exclude_none=True));store.save_session(s);return public_session(s)

    @app.delete('/api/sessions/{sid}')
    async def delete_session(sid:str,delete_evidence:bool=False):
        async with locked(sid):store.delete_session(sid,delete_evidence)
        locks.pop(sid,None)
        return {'ok':True}

    @app.post('/api/sessions/{sid}/upload')
    async def upload(sid:str,files:List[UploadFile]=File(...)):
        async with locked(sid) as s:
            if s.get('demo'):raise HTTPException(400,'请新建真实对话上传图片。')
            if len(files)>12 or len(files)+len(s['attachments'])>24:raise HTTPException(400,'一次最多 12 张，每次对话最多 24 张图片。')
            staged=[]
            for f in files:
                raw=await f.read(12*1024*1024+1)
                if len(raw)>12*1024*1024:raise HTTPException(400,'每张图片最大 12 MB。')
                mime=f.content_type
                valid=(mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') or
                    mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff') or
                    mime=='image/webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
                if not valid:raise HTTPException(400,'请上传 PNG、JPEG 或 WebP 图片；PDF 页面请先截图。')
                aid=uid();staged.append((dict(id=aid,name=Path(f.filename or '题目图片').name[:150],url='/api/attachments/'+aid,mime=mime,extracted=False),raw))
            for attachment,raw in staged:
                target=store.attachments/attachment['id'];target.write_bytes(raw);os.chmod(target,0o600)
                s['attachments'].append(attachment)
            s['messages'].append(message('user','上传了 '+str(len(staged))+' 张已作答题目图片。'))
            store.save_session(s);return public_session(s)

    @app.get('/api/attachments/{aid}')
    def attachment(aid:str):
        for s in store.sessions(full=True):
            for a in s['attachments']:
                if a['id']==aid and (store.attachments/aid).is_file():
                    return FileResponse(store.attachments/aid,media_type=a['mime'],headers={'Cache-Control':'no-store'})
        raise HTTPException(404,'原图已清理或不存在。')

    @app.delete('/api/sessions/{sid}/attachments/{aid}')
    async def remove_attachment(sid:str,aid:str):
        async with locked(sid) as s:
            a=next((a for a in s['attachments'] if a['id']==aid),None)
            if not a:raise HTTPException(404,'原图不存在。')
            (store.attachments/aid).unlink(missing_ok=True)
            a.update(deleted=True,url=None)
            store.save_session(s);return public_session(s)

    @app.post('/api/sessions/{sid}/analyze')
    async def analyze(sid:str):return await operation(sid,service.analyze)

    @app.post('/api/sessions/{sid}/messages')
    async def chat(sid:str,body:Text):return await operation(sid,lambda s:service.chat(s,body.text,body.question_id))

    @app.patch('/api/sessions/{sid}/questions/{qid}')
    async def edit_question(sid:str,qid:str,body:QuestionPatch):
        async with locked(sid) as s:
            q=service.question(s,qid);q.update(body.model_dump(exclude_none=True))
            q.pop('analysis',None);q.pop('solution',None);q['revealed']=False
            store.retract(sid,qid)
            for attempt in q.get('attempts',[]):
                store.retract(sid,attempt['id']);attempt['disputed']=True
            for m in s['messages']:
                if m.get('quiz',{}).get('source',{}).get('question_id')==qid:
                    store.retract(sid,m['quiz']['id']);m['quiz']['disputed']=True
            store.save_session(s);return public_session(s)

    @app.post('/api/sessions/{sid}/questions/{qid}/reveal')
    async def reveal(sid:str,qid:str):
        async with locked(sid) as s:
            q=service.question(s,qid);q.update(revealed=True,help_seen=True);store.save_session(s)
            return public_session(s)

    @app.post('/api/sessions/{sid}/train')
    async def train(sid:str,body:Train):
        return await operation(sid,lambda s:service.train(s,body.question_id,body.knowledge_id,body.purpose))

    @app.post('/api/sessions/{sid}/quiz/{quizid}/answer')
    async def answer(sid:str,quizid:str,body:Answer):
        return await operation(sid,lambda s:service.answer_quiz(s,quizid,body.answer,body.reasoning))

    @app.post('/api/sessions/{sid}/quiz/{quizid}/reveal')
    async def reveal_quiz(sid:str,quizid:str):
        async with locked(sid) as s:
            quiz=next((m['quiz'] for m in s['messages'] if m.get('quiz',{}).get('id')==quizid),None)
            if not quiz:raise HTTPException(404,'验证题不存在。')
            quiz.update(revealed=True,help_kind='assisted')
            store.save_session(s);return public_session(s)

    @app.post('/api/sessions/{sid}/quiz/{quizid}/recheck')
    async def recheck_quiz(sid:str,quizid:str,body:Text):
        return await operation(sid,lambda s:service.recheck_quiz(s,quizid,body.text))

    @app.post('/api/sessions/{sid}/questions/{qid}/retry')
    async def retry_question(sid:str,qid:str,body:Answer):
        return await operation(sid,lambda s:service.retry_question(s,qid,body.answer,body.reasoning))

    @app.post('/api/sessions/{sid}/questions/{qid}/recheck')
    async def recheck(sid:str,qid:str,body:Text):
        return await operation(sid,lambda s:service.recheck(s,qid,body.text))

    @app.post('/api/sessions/{sid}/reference')
    async def reference(sid:str,body:Text):
        async with locked(sid) as s:
            s.setdefault('references',[]).append(dict(id=uid(),text=body.text))
            s['messages'].append(message('user','补充参考资料：\n'+body.text))
            s['messages'].append(message('assistant','已保存参考资料，将用于后续相关讨论与训练。若涉及原判定错误，请选择题目并发起复核。'))
            store.save_session(s);return public_session(s)

    @app.post('/api/sessions/{sid}/reference-upload')
    async def reference_upload(sid:str,files:List[UploadFile]=File(...)):
        import base64
        async with locked(sid) as s:
            if s.get('demo'):raise HTTPException(400,'请新建真实对话补充资料。')
            if not files or len(files)>4:raise HTTPException(400,'一次请补充 1～4 张相关资料截图。')
            inputs=[];attachments=[]
            for f in files:
                raw=await f.read(12*1024*1024+1)
                if len(raw)>12*1024*1024:raise HTTPException(400,'每张图片最大 12 MB。')
                mime=f.content_type
                valid=(mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') or
                    mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff') or
                    mime=='image/webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
                if not valid:raise HTTPException(400,'请使用 PNG、JPEG 或 WebP 资料截图。')
                aid=uid();name=Path(f.filename or '资料截图').name[:150]
                inputs.append(dict(name=name,data_url='data:'+mime+';base64,'+base64.b64encode(raw).decode()))
                attachments.append((dict(id=aid,name=name,mime=mime,url='/api/attachments/'+aid,reference=True,extracted=True),raw))
            try: result=await service.gateway().extract_reference(inputs)
            except Exception:
                raise HTTPException(502,'资料识别未完成，请核对图片模型设置后重新上传。')
            for a,raw in attachments:
                path=store.attachments/a['id'];path.write_bytes(raw);os.chmod(path,0o600);s['attachments'].append(a)
            s.setdefault('references',[]).append(dict(id=uid(),text=result['content'],attachment_ids=[a['id'] for a,_ in attachments]))
            s['messages'].append(message('user','补充资料截图（识别结果可作为后续参考）：\n'+result['content']))
            store.save_session(s);return public_session(s)

    @app.get('/api/knowledge')
    def knowledge():return store.knowledge()

    @app.get('/api/framework')
    def framework():return dict(subjects=['电路','电机学','电力系统分析','继电保护','高电压技术','电气设备','其他专业科目'],note='通用科目框架；具体章节与知识点随刷题积累，可通过参考资料补充考试范围。')

    @app.get('/api/settings')
    def settings():return store.settings(public=True)

    @app.put('/api/settings')
    def update_settings(body:Settings):
        try:return store.save_settings(body.model_dump())
        except ValueError as e:raise HTTPException(422,str(e))

    @app.post('/api/settings/test')
    async def test_profile(body:TestProfile):
        settings=store.settings()
        if not any(p['id']==body.profile_id for p in settings['profiles']):raise HTTPException(404,'模型配置不存在。')
        settings['tasks']={k:body.profile_id for k in TASKS}
        try:
            await gateway_factory(settings).chat({},'请只回复“连接成功”。','direct')
            return {'ok':True,'message':'连接成功，已收到并校验模型响应。'}
        except Exception:
            return {'ok':False,'message':'连接未通过。请核对接口地址、模型名称、密钥及结构化输出支持情况。'}

    @app.post('/api/demo')
    def demo():return public_session(create_demo(store))

    dist=ROOT/'web'/'dist'
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

    @app.get('/')
    def index():
        if (dist/'index.html').exists():return FileResponse(dist/'index.html')
        return JSONResponse({'message':'网页尚未构建，请执行 npm --prefix web run build。'},status_code=503)
    return app
