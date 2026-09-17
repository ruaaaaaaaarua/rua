"""Fixed learning workflow: retrieve Wiki, solve, attach, record observable facts."""
import asyncio
import base64
import copy
import json

from .knowledge import KnowledgeLibrary, SUBJECT
from .models import Option, validate_choice_answer
from .providers import ProviderError
from .store import message, normalized_answer, uid
from .study import StudyRecords, later
from .archive import Archive
from .classification import validate_classification
from .personal import related_history


def public_session(session):
    s = copy.deepcopy(session)
    s.pop('solutions', None)
    for q in s.get('questions', []):
        q.pop('solution', None)
        q.pop('reasoning', None)
        q.pop('confidence', None)
        q.pop('retrieval_audit', None)
        if not q.get('revealed'):
            q.pop('related_history', None)
        a = q.get('analysis') or {}
        for key in ('diagnosis', 'distinction', 'error_type', 'reasoning_ok', 'hint'):
            a.pop(key, None)
        if a and a.get('schema_version') != 3:
            q['legacy'] = True
    # Old generated exercises remain in SQLite backups/history but are not active learning content.
    s['messages'] = [m for m in s.get('messages', []) if not m.get('quiz')]
    s['mode'] = 'direct'
    return s


class LearningService:
    def __init__(self, store, gateway_factory, knowledge_dir=None):
        self.store = store
        self.gateway_factory = gateway_factory
        self.library = KnowledgeLibrary(knowledge_dir)
        self.study = StudyRecords(store, self.library)
        self.archive = Archive(store, self.study)

    def gateway(self):
        gateway = self.gateway_factory(self.store.settings())
        gateway.observer = self.store.record_call
        return gateway

    def question(self, session, qid):
        for q in session['questions']:
            if q['id'] == qid:
                return q
        raise ValueError('没有找到这道题')

    @staticmethod
    def extraction_signature(question):
        return json.dumps({k: question.get(k) for k in ('number', 'kind', 'text', 'options')},
                          ensure_ascii=False, sort_keys=True)

    def cached_extraction(self, cached, ordinal, question):
        if ordinal > len(cached):
            question['extraction_signature'] = self.extraction_signature(question)
            return False
        previous = cached[ordinal - 1]
        signature = previous.get('extraction_signature', self.extraction_signature(previous))
        if signature != self.extraction_signature(question):
            raise ProviderError('重试识别结果与已保存题目不一致，已保留原记录。请核对题目，或在新学习中重新上传。')
        return True

    def prepare_question(self, session, question):
        question.setdefault('revision', 1)
        question['subject'] = question.get('subject') or SUBJECT
        if question['subject'] not in (SUBJECT, '待归类'):
            question['scope_note'] = '当前知识库仅覆盖电力系统分析；本题暂不自动归类。'
            question.setdefault('candidates', [])
            return
        self.study.match(session, question)

    def decorate(self, session):
        for q in session['questions']:
            q['links'] = self.study.links(session['id'], q['id'])
            q.setdefault('candidates', [])
            if q.get('related_history'):
                valid = []
                for item in q['related_history'][:2]:
                    source = self.store.get_session(item['session_id'])
                    other = next((x for x in (source or {}).get('questions', [])
                                  if x['id'] == item['question_id']), None)
                    if other and other.get('revision', 1) == item['revision'] and self.is_confirmed(other):
                        valid.append(item)
                q['related_history'] = valid
        return session

    def wiki_context(self, question=None, text='', kid=None):
        ids = [l['knowledge_id'] for l in (question or {}).get('links', [])]
        if kid:
            ids.append(kid)
        return self.library.context(text or (question or {}).get('text', ''), ids)

    def classification_catalog(self):
        return [{"id": node["id"], "name": node["name"]} for node in self.library.catalog()["nodes"]]

    @staticmethod
    def citations(context):
        return [{k: n[k] for k in ('id', 'name', 'version')} for n in context]

    async def extract_stream(self,s):
        from .models import ExtractedQuestion
        from .providers import ProviderError

        if s.get('demo'): return
        if not s['attachments'] and not s['questions']: raise ValueError('请先上传题目图片。')
        pending=[a for a in s['attachments'] if not a.get('reference') and not a.get('extracted') and not a.get('deleted')]
        if not pending:
            s.update(status='extracted',error=None); self.store.save_session(s)
            yield {'type':'done'}
            return
        s.update(status='recognizing',error=None); self.store.save_session(s)
        gateway=self.gateway()
        saved=0
        for attachment in pending:
            blob=(self.store.attachments/attachment['id']).read_bytes()
            data='data:'+attachment['mime']+';base64,'+base64.b64encode(blob).decode()
            buffer=''; complete=False; ordinal=0
            cached=[q for q in s['questions'] if q.get('attachment_id')==attachment['id']]

            def parse_line(line):
                try: event=json.loads(line)
                except (TypeError,ValueError): raise ProviderError('模型流式识别格式不符合要求，请重试') from None
                if event.get('type')=='done': return None
                if event.get('type')!='question':
                    raise ProviderError('模型流式识别格式不符合要求，请重试')
                try: return ExtractedQuestion.model_validate(event.get('question')).model_dump()
                except Exception: raise ProviderError('模型流式识别格式不符合要求，请重试') from None

            async for part in gateway.stream_extract([dict(data_url=data,name=attachment['name'])]):
                buffer+=part
                while '\n' in buffer:
                    line,buffer=buffer.split('\n',1); line=line.strip()
                    if not line: continue
                    if complete:
                        raise ProviderError('模型流式识别格式不符合要求，请重试')
                    question=parse_line(line)
                    if question is None:
                        complete=True; continue
                    ordinal+=1
                    if self.cached_extraction(cached, ordinal, question): continue
                    question.update(id=uid(),attachment_id=attachment['id'],revealed=False)
                    self.prepare_question(s, question); s['questions'].append(question)
                    self.store.save_session(s); saved+=1
                    yield {'type':'question','question':question}
            if buffer.strip():
                if complete:
                    raise ProviderError('模型流式识别格式不符合要求，请重试')
                question=parse_line(buffer.strip())
                buffer=''
                if question is None:
                    complete=True
                else:
                    ordinal+=1
                    if not self.cached_extraction(cached, ordinal, question):
                        question.update(id=uid(),attachment_id=attachment['id'],revealed=False)
                        self.prepare_question(s, question); s['questions'].append(question)
                        self.store.save_session(s); saved+=1
                        yield {'type':'question','question':question}
            if buffer.strip() or not complete or ordinal < len(cached):
                raise ProviderError('模型流式识别未完整结束，请重试')
            attachment['extracted']=True; self.store.save_session(s)
        if not s['questions']: raise ProviderError('未识别到题目，请确认图片清晰且包含完整题目')
        s.update(status='extracted',error=None); self.store.save_session(s)
        yield {'type':'done'}

    async def extract(self,s):
        if s.get('demo'): return s
        if not s['attachments'] and not s['questions']: raise ValueError('请先上传题目图片。')
        s.update(status='recognizing',error=None); self.store.save_session(s)
        gateway=self.gateway()
        # Each successfully extracted attachment remains cached after failures.
        for a in s['attachments']:
            if a.get('reference') or a.get('extracted') or a.get('deleted'): continue
            blob=(self.store.attachments/a['id']).read_bytes()
            data='data:'+a['mime']+';base64,'+base64.b64encode(blob).decode()
            extracted=await gateway.extract([dict(data_url=data,name=a['name'])])
            cached=[q for q in s['questions'] if q.get('attachment_id')==a['id']]
            if len(extracted) < len(cached):
                raise ProviderError('重试识别题目数量减少，已保留原记录，请核对图片后重试')
            for ordinal, q in enumerate(extracted, 1):
                if self.cached_extraction(cached, ordinal, q): continue
                q.update(id=uid(),attachment_id=a['id'],revealed=False)
                self.prepare_question(s, q)
                s['questions'].append(q)
            a['extracted']=True
            self.store.save_session(s)
        s.update(status='extracted',error=None); self.store.save_session(s)
        return s


    async def analyze(self, s):
        if s.get('demo'):
            raise ValueError('旧演示仅供历史查看，请新建学习')
        if not s['attachments'] and not s['questions']:
            raise ValueError('请先上传题目图片')
        if any(not a.get('reference') and not a.get('extracted') and not a.get('deleted') for a in s['attachments']):
            await self.extract(s)
        gateway = self.gateway()
        s.update(status='analyzing', error=None)
        self.store.save_session(s)
        pending = [q for q in s['questions'] if q.get('analysis', {}).get('status') != 'confirmed'
                   or q.get('analysis', {}).get('schema_version') != 3]
        failures = []
        parallel_for = getattr(gateway, 'parallel_for', None)
        semaphore = asyncio.Semaphore(parallel_for('solve') if callable(parallel_for) else 1)

        async def solve_one(q):
            self.prepare_question(s, q)
            context = self.wiki_context(q)
            task = {**q, 'wiki_context': context, 'reference_note': json.dumps(self.references(s, q['id']), ensure_ascii=False),
                    'classification_catalog': self.classification_catalog()}
            try:
                async with semaphore:
                    solution = await gateway.solve(task)
                self.save_solution(s, q, solution, context)
            except (ProviderError, ValueError) as exc:
                q['analysis'] = dict(schema_version=3, status='pending', correct=None, explanation=str(exc),
                                     answer='', source='model', citations=[], knowledge_status='empty')
                failures.append(str(q.get('number') or '未编号'))
            self.store.save_session(s)

        await asyncio.gather(*(solve_one(q) for q in pending))
        s.update(status='error' if failures else 'ready',
                 error='部分题目未完成，可重试：' + '、'.join(failures) if failures else None)
        if not any(m['type'] == 'overview' for m in s['messages']):
            s['messages'].append(message('assistant', '题目已整理。可以查看讲解、关联知识点，或在之后回顾原题。', 'overview'))
        self.store.save_session(s)
        return self.decorate(s)

    @staticmethod
    def is_confirmed(q):
        a = q.get('analysis') or {}
        return a.get('schema_version') == 3 and a.get('status') == 'confirmed'

    @staticmethod
    def incomplete_question(q):
        return q.get('incomplete', False) or (q['kind'] in {'single', 'multiple'} and len(q.get('options', [])) < 2)

    def save_solution(self, s, q, solution, context):
        if self.incomplete_question(q):
            solution = dict(answer='', valid=False, status='pending',
                explanation='题干、选项或必要图形不完整，请补全识别内容或重新拍照后核对。')
        valid = solution.get('valid', True) and solution.get('status', 'confirmed') == 'confirmed'
        if valid:
            validate_choice_answer(q['kind'], [Option.model_validate(o) for o in q.get('options', [])], solution['answer'])
        supplied = bool(q.get('user_answer'))
        q['analysis'] = dict(schema_version=3, status='confirmed' if valid else 'pending',
            answer=solution.get('answer', ''), explanation=solution.get('explanation', ''),
            correct=normalized_answer(q['user_answer'], q['kind']) == normalized_answer(solution.get('answer'), q['kind']) if supplied and valid else None,
            source='wiki' if context else 'model', citations=self.citations(context),
            knowledge_status='available' if context else 'empty')
        q['retrieval_audit'] = {'core': [{k: n[k] for k in ('id', 'version')} for n in context],
                                'provider': self.provider_identity('solve'), 'history': []}
        if valid and q.get('classification', {}).get('source') != 'manual':
            try:
                classification = validate_classification(solution.get('classification'),
                    {node['id'] for node in self.library.catalog()['nodes']})
            except (TypeError, ValueError):
                classification = None
            if classification:
                classification['source'] = 'ai'
                q['classification'] = classification
                if not q.get('links_managed'):
                    self.study.attach(s, q, classification['knowledge_ids'], source='classified', managed=False)
        self.study.record_solution(s, q)
        self.store.save_session(s)

    async def solve_group(self, s, questions, gateway):
        """Batch only independent question snapshots; retry only absent/invalid rows."""
        complete = []
        for q in questions:
            if self.incomplete_question(q):
                self.save_solution(s, q, {}, [])
            else:
                complete.append(q)
        questions = complete
        tasks, contexts = [], []
        for q in questions:
            self.prepare_question(s, q)
            context = self.wiki_context(q)
            contexts.append(context)
            tasks.append(copy.deepcopy({**q, 'wiki_context': context, 'classification_catalog': self.classification_catalog(),
                'reference_note': json.dumps(self.references(s, q['id']), ensure_ascii=False)}))
        rows = {}
        if len(tasks) > 1 and callable(getattr(gateway, 'solve_batch', None)):
            try:
                result = await gateway.solve_batch(tasks)
                duplicates = set()
                for row in result:
                    index = row.get('index')
                    if not isinstance(index, int) or not 0 <= index < len(tasks):
                        continue
                    if not row.get('valid', True) or row.get('status', 'confirmed') != 'confirmed':
                        continue
                    if index in rows:
                        duplicates.add(index)
                    rows[index] = row
                for index in duplicates:
                    rows.pop(index, None)
            except ProviderError:
                pass  # One bounded individual retry per item, never restart successes.
        for index, q in enumerate(questions):
            if index in rows:
                try:
                    self.save_solution(s, q, rows[index], contexts[index])
                    continue
                except (ValueError, KeyError):
                    pass
            try:
                solution = await gateway.solve(tasks[index])
                self.save_solution(s, q, solution, contexts[index])
            except (ProviderError, ValueError) as exc:
                q['analysis'] = dict(schema_version=3, status='pending', correct=None, answer='',
                    explanation=str(exc), source='model', citations=[], knowledge_status='empty')
                self.store.save_session(s)

    def reveal(self, s, qid):
        q = self.question(s, qid)
        if not self.is_confirmed(q):
            raise ValueError('请先完成题目核对，再查看解析')
        q.update(revealed=True, help_seen=True)
        self.study.mark_viewed(s['id'], qid)
        self.store.save_session(s)
        return self.decorate(s)

    @staticmethod
    def references(s, qid=None):
        return [r for r in s.get('references', []) if not r.get('question_id') or r.get('question_id') == qid][-5:]

    @staticmethod
    def thread_messages(s, q=None):
        return [m for m in s['messages'] if m.get('question_id') == (q or {}).get('id')
                and (not q or m.get('question_revision') == q.get('revision', 1))]

    async def hint(self, s, qid):
        q=self.question(s, qid)
        if q.get('analysis', {}).get('status') != 'confirmed' or q.get('analysis', {}).get('schema_version') != 3:
            raise ValueError('请先完成题目核对，再获取提示')
        if any(m['type']=='hint' for m in self.thread_messages(s, q)):
            q['help_seen']=True
            self.study.mark_viewed(s['id'], qid)
            s.update(status='ready', error=None)
            self.store.save_session(s)
            return self.decorate(s)
        return await self.chat(s, '先给我一点提示，不要直接告诉我答案。', qid, hint=True)

    async def chat(self, s, text, qid=None, kid=None, hint=False):
        async for event in self.chat_events(s, text, qid, kid, hint, stream=False):
            if event['type'] == 'done':
                return event['session']

    async def chat_events(self, s, text, qid=None, kid=None, hint=False, stream=True):
        q = self.question(s, qid) if qid else None
        if s.get('processing') and (not q or not self.is_confirmed(q)):
            raise ValueError('后台整理期间，请先选择已完成核对的题目进行讨论')
        context = self.wiki_context(q, text, kid)
        thread=self.thread_messages(s, q)
        hint_only=bool(hint or (q and not q.get('revealed') and thread and thread[-1].get('hint_only')))
        tags=dict(question_id=qid, question_revision=q.get('revision', 1) if q else None, hint_only=hint_only)
        if not s.get('processing'):
            s.update(status='chatting', error=None)
        s['messages'].append(message('user', text, **tags))
        self.store.save_session(s)
        related_ids = [n['id'] for n in context]
        if kid and kid not in related_ids:
            related_ids.append(kid)
        visible_questions=public_session(s)['questions']
        for item in visible_questions:
            if item.get('legacy'):
                item.pop('analysis', None)
        payload = dict(
            questions=[item for item in visible_questions if item['id']==qid] if q else visible_questions,
            history=self.thread_messages(s, q)[-12:], wiki_context=context, hint_only=hint_only,
            learning=[dict(knowledge_id=k, **self.study.learning(k)) for k in related_ids],
            references=self.references(s, qid))
        history = related_history(self.store, self.study, s['id'], q) if q and q.get('revealed') and not hint_only else []
        if history:
            payload['related_history'] = history
            q['related_history'] = [{k: item[k] for k in ('session_id', 'question_id', 'revision', 'title', 'state', 'source_url')}
                                    for item in history]
        if q:
            q['retrieval_audit'] = {'core': [{k: n[k] for k in ('id', 'version')} for n in context],
                                    'provider': self.provider_identity('chat'),
                                    'history': [{k: item[k] for k in ('session_id', 'question_id', 'revision')} for item in history]}
        # Freeze model context before background work can append later questions/results.
        payload = copy.deepcopy(payload)
        affected = list([q] if q else s['questions'])
        exposed = False
        complete = False

        def expose():
            nonlocal exposed
            if exposed:
                return
            for item in affected:
                item['help_seen'] = True
                self.study.mark_viewed(s['id'], item['id'])
            exposed = True
            self.store.save_session(s)

        try:
            gateway = self.gateway()
            if stream and not hint_only and callable(getattr(gateway, 'stream_chat', None)):
                parts = []
                async for part in gateway.stream_chat(payload, text, 'direct'):
                    if part:
                        expose()
                        parts.append(part)
                        yield {'type': 'delta', 'text': part}
                content = ''.join(parts)
                if not content.strip():
                    raise ProviderError('模型没有返回讲解，请重试', 'response_schema')
            else:
                reply = await gateway.chat(payload, text, 'hint' if hint_only else 'direct')
                content = reply['content']
                if hint_only:
                    import re
                    if re.search(r'(?:答案|选择|选项|应选|选)\s*(?:是|为|：|:)?\s*[A-H](?![a-z])', content):
                        content='先检查题目给定条件与相关概念的适用范围，再尝试下一步推导。需要完整说明时可以点击“查看解析”。'
                expose()
                if stream:
                    yield {'type': 'delta', 'text': content}
            s['messages'].append(message('assistant', content, 'hint' if hint else 'text', citations=self.citations(context),
                                        knowledge_status='available' if context else 'empty', **tags))
            if s['status'] == 'chatting':
                s.update(status='ready', error=None)
            s.pop('chat_error', None)
            self.store.save_session(s)
            complete = True
            yield {'type': 'done', 'session': self.decorate(s)}
        finally:
            if not complete:
                s['chat_error'] = '讲解未完整返回，可重新追问；已看到的内容计为获得帮助。' if exposed else '讲解未完成，可重新追问。'
                if s['status'] == 'chatting':
                    s.update(status='ready')
                self.store.save_session(s)

    def invalidate(self, s, q):
        self.study.invalidate(s['id'], q['id'])
        self.store.retract(s['id'], q['id'])
        q['revision'] = q.get('revision', 1) + 1
        q.pop('analysis', None)
        q.pop('solution', None)
        q.pop('classification', None)
        q.pop('related_history', None)
        q.pop('retrieval_audit', None)
        q['revealed'] = False
        # Do not erase prior exposure when an answer or transcript is corrected.
        q.setdefault('help_seen', False)

    def provider_identity(self, task):
        settings = self.store.settings()
        ident = settings.get('tasks', {}).get(task)
        profile = next((p for p in settings.get('profiles', []) if p.get('id') == ident), {})
        return {k: profile.get(k, '') for k in ('id', 'name', 'model')}

    def set_classification(self, s, q, value):
        data = validate_classification(value, {node['id'] for node in self.library.catalog()['nodes']})
        data['source'] = 'manual'
        q['classification'] = data
        # The explicit correction itself is the authoritative user choice.
        self.study.attach(s, q, data['knowledge_ids'], source='classification-manual', managed=True)
        self.store.save_session(s)
        return self.decorate(s)

    async def organize(self, scoped=None):
        candidates = []
        for s in self.store.sessions(full=True):
            for q in s.get('questions', []):
                if self.is_confirmed(q) and not q.get('classification') and (not scoped or q['id'] in scoped):
                    candidates.append((s, q, q.get('revision', 1)))
        candidates = candidates[:12]
        classified = failed = 0
        gateway = self.gateway()
        parallel_for = getattr(gateway, 'parallel_for', None)
        semaphore = asyncio.Semaphore(min(4, parallel_for('solve') if callable(parallel_for) else 2))

        async def classify_one(candidate):
            s, q, revision = candidate
            try:
                task = {**q, 'wiki_context': self.wiki_context(q), 'classification_catalog': self.classification_catalog()}
                async with semaphore:
                    result = await gateway.solve(task)
                data = validate_classification(result.get('classification'),
                    {node['id'] for node in self.library.catalog()['nodes']})
                return candidate, data
            except Exception:
                return candidate, None

        results = await asyncio.gather(*(classify_one(candidate) for candidate in candidates))
        for (s, q, revision), data in results:
            try:
                if not data:
                    failed += 1
                    continue
                current = self.store.get_session(s['id'])
                current_q = self.question(current, q['id'])
                if current_q.get('revision', 1) != revision or current_q.get('classification'):
                    failed += 1
                    continue
                data['source'] = 'ai'
                current_q['classification'] = data
                if not current_q.get('links_managed'):
                    self.study.attach(current, current_q, data['knowledge_ids'], source='classified', managed=False)
                self.store.save_session(current)
                classified += 1
            except Exception:
                failed += 1
        remaining = sum(1 for s in self.store.sessions(full=True) for q in s.get('questions', [])
                        if self.is_confirmed(q) and not q.get('classification'))
        return {'classified': classified, 'remaining': remaining, 'failed': failed}

    async def review_hint(self, rid):
        run, q = self.study.prepare_hint(rid)
        if run.get('hint'):
            return {**run, 'hint': run['hint'], 'help_kind': 'assisted'}
        gateway = self.gateway()
        payload = {'questions': [{k: q[k] for k in ('id', 'text', 'kind', 'options', 'number') if k in q}],
                   'history': [], 'wiki_context': self.wiki_context(q), 'hint_only': True,
                   'learning': [], 'references': []}
        reply = await gateway.chat(payload, '给一条不透露答案的提示。', 'hint')
        import re
        content = reply['content']
        if re.search(r'(?:答案|选择|选项|应选|选)\s*(?:是|为|：|:)?\s*[A-H](?![a-z])', content):
            content = '先检查题目给定条件与相关概念的适用范围，再尝试下一步推导。'
        self.study.cache_hint(run, content)
        return {**run, 'hint': content, 'help_kind': 'assisted'}

    async def recheck(self, s, qid, text):
        q = self.question(s, qid)
        self.invalidate(s, q)
        s.setdefault('references', []).append(dict(id=uid(), text=text, question_id=qid))
        self.store.save_session(s)
        return await self.analyze(s)

    async def retry_question(self, s, qid, answer):
        q = self.question(s, qid)
        a = q.get('analysis', {})
        if a.get('schema_version') != 3 or a.get('status') != 'confirmed':
            raise ValueError('请先完成题目解答或复核')
        validate_choice_answer(q['kind'], [Option.model_validate(o) for o in q.get('options', [])], answer)
        correct = normalized_answer(answer, q['kind']) == normalized_answer(a['answer'], q['kind'])
        help_kind = 'assisted' if q.get('help_seen') or q.get('revealed') or q.get('user_answer') else 'independent'
        self.study.event(s['id'], qid, 'answer', correct=correct, help_kind=help_kind, next_due_at=later(1))
        q.setdefault('attempts', []).append(dict(id=uid(), answer=answer, correct=correct, help_kind=help_kind))
        q.update(revealed=True, help_seen=True)
        self.study.mark_viewed(s['id'], qid)
        # The original answer is immutable; this response is a separate attempt.
        s['messages'].append(message('assistant', ('本次答对。' if correct else '本次答错，可查看讲解。') +
                                    (' 已记录为得到帮助后的作答。' if help_kind == 'assisted' else ' 已记录本次作答。'),
                                    question_id=qid, question_revision=q.get('revision', 1)))
        self.store.save_session(s)
        return self.decorate(s)
