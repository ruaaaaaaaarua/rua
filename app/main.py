"""Local HTTP boundary; private data never needs a remote application server."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .store import Store, TASKS, message, uid
from .service import LearningService, public_session
from .images import normalize_image, MAX_INPUT_BYTES
from .jobs import StudyJobs
from .archive import MEDALS
from .classification import Classification, taxonomy
from .personal import linked_ids, safe_node

ROOT=Path(__file__).resolve().parent.parent

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class SessionInput(Input):
    title: str=Field(default='新的学习',max_length=100)
    mode: Optional[Literal['direct']]=None

class SessionPatch(Input):
    title: Optional[str]=Field(default=None,max_length=100)
    mode: Optional[Literal['direct']]=None

class Text(Input):
    text: str=Field(min_length=1,max_length=30000)
    question_id: Optional[str]=None
    knowledge_id: Optional[str]=None

class Option(Input):
    key:str=Field(min_length=1,max_length=8)
    text:str=Field(max_length=8000)

class QuestionPatch(Input):
    text:Optional[str]=Field(default=None,min_length=1,max_length=20000)
    options:Optional[List[Option]]=None
    user_answer:Optional[str]=Field(default=None,max_length=200)
    kind:Optional[Literal['single','multiple','judge']]=None
    completeness_confirmed:bool=False

class Answer(Input):
    answer:str=Field(min_length=1,max_length=200)

class Links(Input):
    knowledge_ids:List[str]=Field(max_length=20)

class ReviewStart(Input):
    session_id:str
    question_id:str

class Organize(Input):
    question_ids:Optional[List[str]]=Field(default=None,max_length=12)

class ArchiveProfile(Input):
    nickname:str=Field(default='学习者',max_length=30)
    signature:str=Field(default='',max_length=100)
    theme:Literal['paper','blueprint']='paper'
    selected_medals:List[str]=Field(default_factory=list,max_length=3)
    show_stats:bool=False

    @field_validator('selected_medals')
    @classmethod
    def valid_medals(cls,value):
        if len(value)!=len(set(value)) or any(v not in MEDALS for v in value):
            raise ValueError('勋章选择无效')
        return value

class Profile(Input):
    id:str=Field(default='',max_length=100)
    name:str=Field(min_length=1,max_length=100)
    base_url:str=Field(min_length=1,max_length=1000)
    model:str=Field(min_length=1,max_length=200)
    api_key:Optional[str]=Field(default=None,max_length=4096)
    has_key:Optional[bool]=None
    remove_key:bool=False
    disable_thinking:bool=False
    parallel:Optional[int]=Field(default=None,ge=1,le=8)

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
    mode:Literal['direct']='direct'
    rate_tpm:Optional[int]=Field(default=None,ge=1000,le=10000000)
    parallel:Optional[int]=Field(default=None,ge=1,le=8)

    @field_validator('tasks')
    @classmethod
    def task_names(cls,v):
        if set(v)!=set(TASKS):raise ValueError('需要配置 vision/solve/chat 三个任务')
        return v

class TestProfile(Input):
    profile_id:str


def create_app(data_dir=None,gateway_factory=None,knowledge_dir=None):
    store=Store(data_dir or os.environ.get('GRID_LEARNING_DATA',ROOT/'data'))
    if gateway_factory is None:
        from .providers import ModelGateway
        gateway_factory=ModelGateway
    service=LearningService(store,gateway_factory,knowledge_dir)
    jobs=StudyJobs(service)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await jobs.close()
    app=FastAPI(title='电力系统分析 · 学习工作台',docs_url='/api/docs',openapi_url='/api/openapi.json',lifespan=lifespan)
    app.state.store=store;app.state.service=service
    app.state.jobs=jobs
    locks={}
    organizing=False

    @app.exception_handler(ValueError)
    async def invalid_operation(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=400)

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
        s=jobs.session(sid) or store.get_session(sid)
        if not s:raise HTTPException(404,'没有找到这次刷题')
        s['processing']=bool(jobs.session(sid))
        return service.decorate(s)

    @asynccontextmanager
    async def locked(sid, background=False):
        lock=locks.setdefault(sid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'当前对话正在处理，请等待完成。')
        if not background and jobs.session(sid):
            raise HTTPException(409,'后台正在整理题目；已完成的题目可以查看、提示和追问，编辑请稍后。')
        async with lock:
            jobs.interactive_start()
            try:
                yield get(sid)
            finally:
                jobs.interactive_end()

    async def operation(sid,fn,background=False):
        async with locked(sid,background=background) as s:
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
    async def session(sid:str):return public_session(get(sid))

    @app.patch('/api/sessions/{sid}')
    async def update_session(sid:str,body:SessionPatch):
        async with locked(sid,background=True) as s:
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
            if len(files)>12:raise HTTPException(400,f'本次选择了 {len(files)} 张图片，一次最多上传 12 张。')
            if len(files)+len([a for a in s['attachments'] if not a.get('deleted')])>24:
                raise HTTPException(400,'这次学习已达到 24 张图片上限，请新建学习或清理不再需要的原图。')
            staged=[]
            for f in files:
                raw=await f.read(MAX_INPUT_BYTES+1)
                try: raw,mime,name=await asyncio.to_thread(normalize_image,raw,f.filename)
                except ValueError as exc:raise HTTPException(400,str(exc))
                aid=uid();staged.append((dict(id=aid,name=name,original_name=Path(f.filename or name).name[:150],url='/api/attachments/'+aid,mime=mime,extracted=False),raw))
            for attachment,raw in staged:
                target=store.attachments/attachment['id'];target.write_bytes(raw);os.chmod(target,0o600)
                s['attachments'].append(attachment)
            s['messages'].append(message('user','上传了 '+str(len(staged))+' 张题目图片。'))
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

    @app.post('/api/sessions/{sid}/process')
    async def process(sid:str):
        if organizing:raise HTTPException(409,'AI 正在整理历史题目，请稍后开始后台处理。')
        async with locked(sid,background=True) as s:
            return public_session(jobs.start(s))

    @app.post('/api/sessions/{sid}/extract')
    async def extract(sid:str):return await operation(sid,service.extract)

    @app.post('/api/sessions/{sid}/extract-stream')
    async def extract_stream(sid:str):
        def sse(event):
            return 'event: '+event['type']+'\ndata: '+json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n\n'

        async def events():
            try:
                async with locked(sid) as s:
                    try:
                        async for event in service.extract_stream(s):
                            yield sse(event)
                    except ValueError as exc:
                        s.update(status='error',error=str(exc));store.save_session(s)
                        yield sse({'type':'error','message':str(exc)})
                    except Exception as exc:
                        from .providers import ProviderError
                        safe=str(exc) if isinstance(exc,ProviderError) else '处理未完成，记录已保存。请检查模型配置后重试。'
                        s.update(status='error',error=safe);store.save_session(s)
                        yield sse({'type':'error','message':safe})
            except HTTPException as exc:
                yield sse({'type':'error','message':str(exc.detail)})

        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store'})

    @app.post('/api/sessions/{sid}/messages')
    async def chat(sid:str,body:Text):return await operation(sid,lambda s:service.chat(s,body.text,body.question_id,body.knowledge_id),background=True)

    @app.post('/api/sessions/{sid}/messages-stream')
    async def chat_stream(sid:str,body:Text):
        def sse(event):
            return 'event: '+event['type']+'\ndata: '+json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n\n'
        async def events():
            try:
                async with locked(sid,background=True) as s:
                    async for event in service.chat_events(s,body.text,body.question_id,body.knowledge_id):
                        if event['type']=='done':
                            event={**event,'session':public_session(event['session'])}
                        yield sse(event)
            except HTTPException as exc:
                yield sse({'type':'error','message':str(exc.detail)})
            except Exception as exc:
                from .providers import ProviderError
                safe=str(exc) if isinstance(exc,(ValueError,ProviderError)) else '讲解未完整返回，请重试。'
                yield sse({'type':'error','message':safe})
        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.patch('/api/sessions/{sid}/questions/{qid}')
    async def edit_question(sid:str,qid:str,body:QuestionPatch):
        async with locked(sid) as s:
            q=service.question(s,qid)
            old_text=q.get('text')
            service.invalidate(s,q)
            q.update(body.model_dump(exclude_none=True,exclude={'completeness_confirmed'}))
            if body.completeness_confirmed:
                q['incomplete']=False
            if body.text is not None and body.text != old_text:
                # OCR labels belong to the old transcript. Do not carry them into a new match.
                q['knowledge']='待归类'
                q['links_managed']=False
            service.prepare_question(s,q)
            store.save_session(s);return public_session(s)

    @app.post('/api/sessions/{sid}/questions/{qid}/reveal')
    async def reveal(sid:str,qid:str):
        async with locked(sid,background=True) as s:
            return public_session(service.reveal(s,qid))

    @app.put('/api/sessions/{sid}/questions/{qid}/links')
    async def attach(sid:str,qid:str,body:Links):
        async with locked(sid) as s:
            q=service.question(s,qid)
            try: service.study.attach(s,q,body.knowledge_ids)
            except ValueError as exc: raise HTTPException(422,str(exc))
            if q.get('classification') and sorted(q['classification'].get('knowledge_ids',[])) != sorted(body.knowledge_ids):
                q.pop('classification',None)
            service.decorate(s);store.save_session(s)
            return public_session(s)

    @app.patch('/api/sessions/{sid}/questions/{qid}/classification')
    async def classify_question(sid:str,qid:str,body:Classification):
        async with locked(sid) as s:
            try:return public_session(service.set_classification(s,service.question(s,qid),body.model_dump()))
            except ValueError as exc:raise HTTPException(422,str(exc))

    @app.post('/api/sessions/{sid}/questions/{qid}/retry')
    async def retry_question(sid:str,qid:str,body:Answer):
        return await operation(sid,lambda s:service.retry_question(s,qid,body.answer),background=True)

    @app.post('/api/sessions/{sid}/questions/{qid}/hint')
    async def hint(sid:str,qid:str):
        return await operation(sid,lambda s:service.hint(s,qid),background=True)

    @app.post('/api/sessions/{sid}/questions/{qid}/recheck')
    async def recheck(sid:str,qid:str,body:Text):
        return await operation(sid,lambda s:service.recheck(s,qid,body.text))

    @app.post('/api/sessions/{sid}/reference')
    async def reference(sid:str,body:Text):
        async with locked(sid) as s:
            s.setdefault('references',[]).append(dict(id=uid(),text=body.text))
            s['messages'].append(message('user','补充参考资料：\n'+body.text))
            s['messages'].append(message('assistant','已保存参考资料，将用于后续相关讨论。若涉及原判定错误，请选择题目并发起复核。'))
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

    @app.get('/api/wiki')
    def wiki(q:str=''):
        visible=linked_ids(service.study,store.sessions(full=True))
        catalog=service.library.catalog()
        nodes=service.library.search(q,200) if q else catalog['nodes']
        return {'subject':catalog['subject'],'version':catalog['version'],'chapters':catalog['chapters'],
                'published_count':sum(n['status']=='published' for n in nodes if n['id'] in visible),
                'nodes':[safe_node(n,visible) for n in nodes if n['id'] in visible]}

    @app.get('/api/wiki/{kid}')
    def wiki_node(kid:str):
        visible=linked_ids(service.study,store.sessions(full=True))
        if kid not in visible:raise HTTPException(404,'知识点尚未与个人题目关联')
        try: node=service.library.get(kid)
        except ValueError as exc: raise HTTPException(404,str(exc))
        return {**safe_node(node,visible,detail=True),'questions':service.study.questions(kid),'learning':service.study.learning(kid)}

    @app.get('/api/knowledge')
    def knowledge():
        visible=linked_ids(service.study,store.sessions(full=True))
        return [dict(id=n['id'],name=n['name'],subject='电力系统分析',chapter=n['chapter_id'],
                     **service.study.learning(n['id'])) for n in service.library.catalog()['nodes'] if n['id'] in visible]

    @app.get('/api/framework')
    def framework():
        return dict(subjects=['电力系统分析'],chapters=service.library.catalog()['chapters'],
                    note='章节与知识点骨架；正文待维护者填充。')

    @app.get('/api/reviews')
    def reviews(limit:int=5):
        if limit not in (3,5,10):raise HTTPException(422,'limit 仅支持 3、5、10')
        return service.study.queue(limit)

    @app.get('/api/review-taxonomy')
    def review_taxonomy():return taxonomy()

    @app.post('/api/reviews/organize')
    async def organize_reviews(body:Organize):
        nonlocal organizing
        if jobs.active or organizing:raise HTTPException(409,'后台整理期间暂不能重新分类。')
        organizing=True
        try:return await service.organize(body.question_ids)
        finally:organizing=False

    @app.post('/api/reviews/start')
    async def start_review(body:ReviewStart):
        async with locked(body.session_id):
            try: return service.study.start(body.session_id,body.question_id)
            except ValueError as exc: raise HTTPException(400,str(exc))

    @app.post('/api/reviews/{rid}/reveal')
    async def reveal_review(rid:str):
        async with locked(service.study.run_session(rid)):
            return service.study.review(rid)

    @app.post('/api/reviews/{rid}/answer')
    async def answer_review(rid:str,body:Answer):
        async with locked(service.study.run_session(rid)):
            return service.study.review(rid,body.answer)

    @app.post('/api/reviews/{rid}/hint')
    async def hint_review(rid:str):
        async with locked(service.study.run_session(rid),background=True):
            try:return await service.review_hint(rid)
            except ValueError as exc:raise HTTPException(400,str(exc))

    @app.get('/api/archive')
    def archive():return service.archive.get()

    @app.put('/api/archive')
    def update_archive(body:ArchiveProfile):
        try:return service.archive.save(body.model_dump())
        except ValueError as exc:raise HTTPException(422,str(exc))

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

    dist=ROOT/'web'/'dist'
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

    @app.get('/')
    def index():
        if (dist/'index.html').exists():return FileResponse(dist/'index.html')
        return JSONResponse({'message':'网页尚未构建，请执行 npm --prefix web run build。'},status_code=503)
    return app
