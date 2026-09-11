"""Local records and auditable knowledge projection. No model owns state."""
import copy
import hashlib
import json
import os
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

TASKS = ('vision', 'solve', 'chat', 'generate', 'verify')


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def normalized_answer(value, kind='single'):
    value = unicodedata.normalize('NFKC', str(value or '')).strip().upper()
    if kind == 'judge':
        if value in ('对','正确','是','√','✓','TRUE','T','1'): return 'TRUE'
        if value in ('错','错误','否','×','✗','FALSE','F','0'): return 'FALSE'
    return ''.join(sorted(set(c for c in value if c.isalpha() or c.isdigit())))


def message(role, content, kind='text', **kwargs):
    return dict(id=uid(), role=role, content=content, type=kind, created_at=now(), **kwargs)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.attachments = self.directory / 'attachments'
        self.attachments.mkdir(exist_ok=True)
        self.database = self.directory / 'learning.sqlite3'
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, session_id TEXT, question_id TEXT,
                knowledge_id TEXT, valid INTEGER NOT NULL, data TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS evidence_source ON evidence(session_id,question_id);
              CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            ''')
        os.chmod(self.database, 0o600)
        # Interrupted remote calls are resumable, never silently considered completed.
        for session in self.sessions(full=True):
            if session['status'] in ('analyzing','training','chatting'):
                session.update(status='error',error='上次处理被中断，已保存内容，可重试。')
                self.save_session(session)

    def connect(self):
        db = sqlite3.connect(str(self.database), timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def create_session(self, title='新的刷题', mode=None, demo=False):
        session = dict(id=uid(),title=title,created_at=now(),updated_at=now(),
            status='ready',mode=mode or self.settings()['mode'],demo=demo,
            messages=[],questions=[],attachments=[],references=[])
        self.save_session(session)
        return session

    def save_session(self, session):
        session['updated_at'] = now()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)',
                (session['id'],json.dumps(session,ensure_ascii=False)))

    def get_session(self, ident):
        with self.connect() as db:
            row=db.execute('SELECT data FROM sessions WHERE id=?',(ident,)).fetchone()
        return json.loads(row['data']) if row else None

    def sessions(self, full=False):
        with self.connect() as db:
            rows=db.execute('SELECT data FROM sessions').fetchall()
        values=sorted((json.loads(r['data']) for r in rows),key=lambda s:s['updated_at'],reverse=True)
        return values if full else [{k:s[k] for k in ('id','title','created_at','updated_at','status','mode','demo')} for s in values]

    def settings(self, public=False):
        with self.connect() as db:
            row=db.execute('SELECT data FROM config WHERE id=1').fetchone()
        settings=json.loads(row['data']) if row else dict(profiles=[],tasks={k:'' for k in TASKS},mode='direct')
        if public:
            for p in settings['profiles']:
                p['has_key']=bool(p.pop('api_key',''))
        return settings

    def record_call(self,event):
        allowed=('task','profile_id','model','input_tokens','output_tokens','duration_ms','success','error_kind')
        clean={k:event.get(k) for k in allowed}
        if 'error_kind' not in event:
            clean.pop('error_kind')
        clean['created_at']=now()
        with self.connect() as db:
            db.execute('INSERT INTO calls VALUES (?,?)',(uid(),json.dumps(clean,ensure_ascii=False)))

    def save_settings(self, settings):
        old={p['id']:p for p in self.settings()['profiles']}
        clean=copy.deepcopy(settings)
        seen=set()
        for p in clean['profiles']:
            p['id']=p.get('id') or uid()
            if p['id'] in seen: raise ValueError('模型配置 ID 重复')
            seen.add(p['id'])
            if p.pop('remove_key',False): p['api_key']=''
            elif not p.get('api_key'): p['api_key']=old.get(p['id'],{}).get('api_key','')
            p.pop('has_key',None)
        if any(v and v not in seen for v in clean['tasks'].values()):
            raise ValueError('任务指定了不存在的模型配置')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO config VALUES (1,?)',(json.dumps(clean),))
        return self.settings(public=True)

    def retract(self, session_id, question_id=None):
        sql='UPDATE evidence SET valid=0 WHERE session_id=?'
        args=[session_id]
        if question_id: sql+=' AND question_id=?'; args.append(question_id)
        with self.connect() as db: db.execute(sql,args)

    def record_evidence(self, session_id, question, attempt_id=None, help_kind='independent', purpose='original'):
        session=self.get_session(session_id)
        if not session or session.get('demo'): return
        analysis=question.get('analysis') or {}
        qid=attempt_id or question['id']
        # Replace prior judgment for this exact source; keeps superseded history auditable.
        self.retract(session_id,qid)
        if analysis.get('status')!='confirmed' or analysis.get('correct') is None: return
        name=question.get('knowledge') or analysis.get('knowledge') or '尚未归类'
        subject=question.get('subject') or '未分类'
        chapter=question.get('chapter') or '未分类'
        key='|'.join((subject,chapter,name)).casefold().replace(' ','')
        kid=hashlib.sha256(key.encode()).hexdigest()[:20]
        data=dict(id=uid(),session_id=session_id,question_id=qid,knowledge_id=kid,
            name=name,subject=subject,chapter=chapter,created_at=now(),
            correct=analysis['correct'],reasoning_ok=analysis.get('reasoning_ok'),
            observation=analysis.get('diagnosis') or analysis.get('knowledge_point') or '本题作答已记录',
            reasoning=question.get('reasoning',''),has_reasoning=bool(question.get('reasoning')),confidence=question.get('confidence','unknown'),
            help_kind=help_kind,purpose=purpose,source_deleted=False,
            question_excerpt=question.get('text','')[:400])
        with self.connect() as db:
            db.execute('INSERT INTO evidence VALUES (?,?,?,?,1,?)',
                (data['id'],session_id,qid,kid,json.dumps(data,ensure_ascii=False)))
        analysis['knowledge_id']=kid

    def knowledge(self):
        with self.connect() as db: rows=db.execute('SELECT valid,data FROM evidence ORDER BY rowid').fetchall()
        groups={}
        for row in rows:
            e=json.loads(row['data']); e['valid']=bool(row['valid'])
            group=groups.setdefault(e['knowledge_id'],{'all':[],'valid':[]})
            group['all'].append(e)
            if e['valid']: group['valid'].append(e)
        result=[]
        for kid,g in groups.items():
            es=g['valid']
            if not es: continue
            last=es[-1]
            # Exploration cannot erase demonstrated fundamentals.
            core=[e for e in es if e['purpose']!='depth']
            base=core[-1] if core else last
            independent=[e for e in core if e['help_kind']=='independent' and e['correct'] and
                         e['confidence'] not in ('unsure','guess') and e['reasoning_ok'] is not False]
            has_problem=not base['correct'] or base['reasoning_ok'] is False or base['confidence'] in ('unsure','guess')
            if has_problem: state='待验证'; summary=base['observation']
            elif base['help_kind']!='independent': state='待独立验证'; summary='得到提示或解析后通过，尚需独立作答证据。'
            elif base['purpose'] in ('verify','prerequisite','variant'):
                state='独立验证通过'; summary='本次针对性验证通过，持续观察其他条件下的表现。'
            elif base.get('reasoning_ok') is True and base.get('has_reasoning',bool(base.get('reasoning'))):
                state='已有理解依据'; summary='本次答案及关键思路正确，尚不足以判断长期稳定。'
            else: state='本题答对'; summary='已记录正确作答，尚无充分的理解与保持证据。'
            independent_dates={e['created_at'][:10] for e in independent}
            # No percentages; require multiple days plus explicit reasoning and no recent problems.
            if not has_problem and len(independent)>=3 and len(independent_dates)>=2 and any(e['reasoning_ok'] is True and e.get('has_reasoning',bool(e.get('reasoning'))) for e in independent):
                last_problem=max((i for i,e in enumerate(core) if not e['correct'] or e['reasoning_ok'] is False), default=-1)
                after=[e for e in core[last_problem+1:] if e in independent]
                if len(after)>=3 and len({e['created_at'][:10] for e in after})>=2:
                    state='表现较稳定'; summary='多次跨日独立作答有一致证据，仍保留适用条件边界。'
            if last['purpose']=='depth' and not last['correct']:
                summary+=' 深入测试的新条件尚待验证，不改变已有基础证据。'
            result.append(dict(id=kid,subject=last['subject'],chapter=last['chapter'],name=last['name'],state=state,
                summary=summary,last_verified=independent[-1]['created_at'] if independent else None,
                evidence_count=len(es),evidence=list(reversed(es)),
                history=[dict(created_at=e['created_at'],summary=e['observation'],valid=e['valid'],correct=e['correct'],help_kind=e['help_kind']) for e in reversed(g['all'])]))
        return sorted(result,key=lambda k:(k['state'] not in ('待验证','待独立验证'),k['subject'],k['chapter']))

    def delete_session(self, ident, delete_evidence=False):
        session=self.get_session(ident)
        if not session: return
        with self.connect() as db:
            if delete_evidence:
                db.execute('DELETE FROM evidence WHERE session_id=?',(ident,))
            else:
                rows=db.execute('SELECT id,data FROM evidence WHERE session_id=?',(ident,)).fetchall()
                for r in rows:
                    e=json.loads(r['data']); e.update(source_deleted=True,question_excerpt='',reasoning='')
                    db.execute('UPDATE evidence SET data=? WHERE id=?',(json.dumps(e,ensure_ascii=False),r['id']))
            db.execute('DELETE FROM sessions WHERE id=?',(ident,))
        for a in session['attachments']:
            (self.attachments/a['id']).unlink(missing_ok=True)
