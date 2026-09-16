"""Local records and auditable knowledge projection. No model owns state."""
import copy
import json
import os
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .providers import normalize_error_kind

TASKS = ('vision', 'solve', 'chat')


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
              CREATE TABLE IF NOT EXISTS daily_sessions(day TEXT PRIMARY KEY, sequence INTEGER NOT NULL);
            ''')
        os.chmod(self.database, 0o600)
        # Interrupted remote calls are resumable, never silently considered completed.
        for session in self.sessions(full=True):
            if session.get('processing') or session['status'] in ('recognizing','analyzing','training','chatting'):
                session.update(status='error',processing=False,job_phase=None,error='上次处理被中断，已保存内容，可重试。')
                self.save_session(session)

    def connect(self):
        db = sqlite3.connect(str(self.database), timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def create_session(self, title=None, mode=None, demo=False):
        if not title or title in ('新的学习', '新的刷题', '学习对话'):
            day=datetime.fromisoformat(now()).astimezone(timezone(timedelta(hours=8))).strftime('%Y%m%d')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR IGNORE INTO daily_sessions VALUES (?,0)',(day,))
                db.execute('UPDATE daily_sessions SET sequence=sequence+1 WHERE day=?',(day,))
                sequence=db.execute('SELECT sequence FROM daily_sessions WHERE day=?',(day,)).fetchone()['sequence']
            title=f'电力系统分析{sequence} · {day[2:]}'
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
        settings['tasks'] = {k: settings.get('tasks', {}).get(k, '') for k in TASKS}
        settings['mode'] = 'direct'
        if public:
            for p in settings['profiles']:
                p['has_key']=bool(p.pop('api_key',''))
        return settings

    def record_call(self,event):
        allowed=('task','profile_id','model','input_tokens','output_tokens','duration_ms','success','error_kind')
        clean={k:event.get(k) for k in allowed}
        if 'error_kind' not in event:
            clean.pop('error_kind')
        else:
            clean['error_kind']=normalize_error_kind(clean['error_kind'])
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

    def delete_session(self, ident, delete_evidence=False):
        session=self.get_session(ident)
        if not session: return
        with self.connect() as db:
            tables={r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'question_links' in tables:
                db.execute('DELETE FROM question_links WHERE session_id=?',(ident,))
            if 'review_runs' in tables:
                for row in db.execute('SELECT id,data FROM review_runs').fetchall():
                    if json.loads(row['data']).get('session_id')==ident:
                        db.execute('DELETE FROM review_runs WHERE id=?',(row['id'],))
            if delete_evidence and 'study_events' in tables:
                db.execute('DELETE FROM study_events WHERE session_id=?',(ident,))
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
