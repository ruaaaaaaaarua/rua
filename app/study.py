"""Personal question links, observable events and deterministic original-question reviews."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Option, validate_choice_answer
from .store import now, uid, normalized_answer

LOCAL_USER = 'local'
INTERVALS = (1, 3, 7, 14, 30)
SHANGHAI = ZoneInfo('Asia/Shanghai')


def local_day(value):
    return datetime.fromisoformat(value).astimezone(SHANGHAI).date().isoformat()


def later(days, clock=None):
    return ((clock or datetime.now(timezone.utc)) + timedelta(days=days)).isoformat()


class StudyRecords:
    def __init__(self, store, library):
        self.store, self.library = store, library
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS question_links (
                    user_id TEXT, session_id TEXT, question_id TEXT, knowledge_id TEXT, source TEXT,
                    PRIMARY KEY(user_id,session_id,question_id,knowledge_id));
                CREATE TABLE IF NOT EXISTS study_events (
                    id TEXT PRIMARY KEY, user_id TEXT, session_id TEXT, question_id TEXT,
                    valid INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS study_event_source ON study_events(user_id,session_id,question_id);
                CREATE TABLE IF NOT EXISTS review_runs (id TEXT PRIMARY KEY, user_id TEXT, data TEXT NOT NULL);
            ''')

    def links(self, sid, qid):
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM question_links WHERE user_id=? AND session_id=? AND question_id=?',
                              (LOCAL_USER, sid, qid)).fetchall()
        nodes = {n['id']: n for n in self.library.catalog()['nodes']}
        return [dict(knowledge_id=r['knowledge_id'], name=nodes[r['knowledge_id']]['name'],
                     chapter_id=nodes[r['knowledge_id']]['chapter_id'], source=r['source'])
                for r in rows if r['knowledge_id'] in nodes]

    def attach(self, session, question, ids, source='manual', managed=True):
        ids = list(dict.fromkeys(ids))
        for ident in ids:
            self.library.get(ident)
        with self.store.connect() as db:
            db.execute('DELETE FROM question_links WHERE user_id=? AND session_id=? AND question_id=?',
                       (LOCAL_USER, session['id'], question['id']))
            db.executemany('INSERT INTO question_links VALUES (?,?,?,?,?)',
                           [(LOCAL_USER, session['id'], question['id'], ident, source) for ident in ids])
        if managed:
            question['links_managed'] = True

    def match(self, session, question):
        exact, candidates = self.library.match(question)
        if not question.get('links_managed'):
            self.attach(session, question, [n['id'] for n in exact], 'matched', managed=False)
        question['candidates'] = [{k: n[k] for k in ('id', 'name', 'chapter_id')} for n in candidates]
        question['links'] = self.links(session['id'], question['id'])

    def event(self, sid, qid, kind, *, event_id=None, **facts):
        data = dict(id=event_id or uid(), kind=kind, created_at=now(), **facts)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO study_events VALUES (?,?,?,?,1,?)',
                       (data['id'], LOCAL_USER, sid, qid, json.dumps(data, ensure_ascii=False)))
        return data

    def events(self, sid, qid):
        with self.store.connect() as db:
            rows = db.execute('SELECT data FROM study_events WHERE user_id=? AND session_id=? AND question_id=? AND valid=1 ORDER BY rowid',
                              (LOCAL_USER, sid, qid)).fetchall()
        return [json.loads(r['data']) for r in rows]

    def invalidate(self, sid, qid):
        with self.store.connect() as db:
            db.execute('UPDATE study_events SET valid=0 WHERE user_id=? AND session_id=? AND question_id=?',
                       (LOCAL_USER, sid, qid))
        # Runs also check source revision on every access; no stale answer can be submitted.

    def record_solution(self, session, question):
        if session.get('demo'):
            return
        analysis = question.get('analysis', {})
        if analysis.get('status') != 'confirmed':
            return
        supplied = bool(question.get('user_answer'))
        self.event(session['id'], question['id'], 'observed_answer' if supplied else 'saved',
                   event_id=f"source:{session['id']}:{question['id']}:{question.get('revision', 1)}",
                   correct=analysis.get('correct'), help_kind='unknown', next_due_at=later(1),
                   revision=question.get('revision', 1),
                   core_versions={item['id']: item['version'] for item in question.get('retrieval_audit', {}).get('core', [])})

    @staticmethod
    def summary(events):
        answers = [e for e in events if e.get('correct') is not None]
        errors = sum(e['correct'] is False for e in answers)
        reviews = [e for e in answers if e['kind'] == 'review_answer']
        state = '尚无作答记录'
        if answers:
            last = answers[-1]
            state = ('近期答错' if not last['correct'] else '辅助后答对' if last.get('help_kind') == 'assisted'
                     else '原题复习通过' if last['kind'] == 'review_answer' else '已记录答对')
        elif any(e['kind'] == 'viewed' for e in events):
            state = '已查看讲解'
        return dict(state=state, event_count=len(events), summary=(
            f'{len(answers)} 次可用作答，{errors} 次错误，{len(reviews)} 次原题复习。'
            '上传前的帮助情况未知；原题表现不代表陌生题能力。'))

    def learning(self, kid):
        events = []
        for s in self.store.sessions(full=True):
            if s.get('demo'):
                continue
            for q in s['questions']:
                if kid in [l['knowledge_id'] for l in self.links(s['id'], q['id'])]:
                    events.extend(self.events(s['id'], q['id']))
        events.sort(key=lambda e: e['created_at'])
        return self.summary(events)

    def questions(self, kid):
        result = []
        for s in self.store.sessions(full=True):
            if s.get('demo'):
                continue
            for q in s['questions']:
                links = self.links(s['id'], q['id'])
                if kid in [l['knowledge_id'] for l in links]:
                    result.append(dict(session_id=s['id'], question_id=q['id'], text=q['text'],
                                       number=q.get('number'), links=links))
        return result

    def queue(self, limit=5):
        from .classification import DIFFICULTIES, METHODS, group_key
        progress = {}
        fingerprints = {}
        items = []
        timestamp = now()
        for s in self.store.sessions(full=True):
            if s.get('demo'):
                continue
            for q in s['questions']:
                analysis = q.get('analysis', {})
                if analysis.get('status') != 'confirmed' or analysis.get('schema_version') != 3:
                    continue
                events = self.events(s['id'], q['id'])
                scheduled = [e for e in events if e.get('next_due_at')]
                if not scheduled:
                    continue
                due_at = scheduled[-1]['next_due_at']
                summary = self.summary(events)
                answers = [e for e in events if e.get('correct') is not None]
                reviews = [e for e in events if e['kind'] == 'review_answer']
                progress[(s['id'], q['id'])] = reviews
                fingerprints[(s['id'], q['id'])] = json.dumps(
                    [q.get('text', '').strip(), q.get('kind'), q.get('options', [])],
                    ensure_ascii=False, sort_keys=True)
                reason = ('最近作答错误，回顾这道原题。' if summary['state'] == '近期答错' else
                          '上次得到帮助后通过，再独立回顾。' if summary['state'] == '辅助后答对' else
                          '按学习记录安排原题回顾；到期不代表已经遗忘。')
                classification = q.get('classification')
                links = self.links(s['id'], q['id'])
                items.append(dict(session_id=s['id'], question_id=q['id'], text=q['text'], number=q.get('number'),
                                  knowledge=[dict(id=l['knowledge_id'], name=l['name']) for l in self.links(s['id'], q['id'])],
                                  due_at=due_at, due=due_at <= timestamp, reason=reason, state=summary['state'],
                                  classification=classification, difficulty=(classification or {}).get('difficulty'),
                                  group_id=group_key(classification, links)))
        items.sort(key=lambda i: i['due_at'])
        groups = {}
        for item in items:
            key = item['group_id'] or f"single:{item['session_id']}:{item['question_id']}"
            item['group_id'] = key
            groups.setdefault(key, []).append(item)
        output_groups = []
        for key, members in groups.items():
            rank = {'basic': 0, 'intermediate': 1, 'advanced': 2}
            available = sorted({rank[i['difficulty']] for i in members if i.get('difficulty') in rank})
            target = (available[0] if available else 0)
            trajectory = [(event, rank.get(item.get('difficulty'), 0)) for item in members
                for event in progress[(item['session_id'], item['question_id'])]]
            trajectory.sort(key=lambda pair: pair[0]['created_at'])
            independent_days = {local_day(event['created_at']) for event, _ in trajectory
                if event.get('correct') and event.get('help_kind') == 'independent'}
            latest = trajectory[-1] if trajectory else None
            progressing = bool(latest and latest[0].get('correct') and
                               latest[0].get('help_kind') == 'independent' and len(independent_days) >= 2)
            if progressing:
                harder = [level for level in available if level > latest[1]]
                target = harder[0] if harder else latest[1]
            representative = sorted(members, key=lambda i: (
                abs(rank.get(i.get('difficulty'), target) - target), not i['due'],
                -rank.get(i.get('difficulty'), 0) if progressing else rank.get(i.get('difficulty'), 0),
                i['state'] not in ('近期答错', '辅助后答对'), i['due_at']))[0]
            classification = representative.get('classification') or {}
            knowledge = representative['knowledge'][0] if representative['knowledge'] else {'id': None, 'name': '未分类'}
            output_groups.append({'id': key, 'knowledge_id': knowledge['id'], 'knowledge_name': knowledge['name'],
                'method': classification.get('method'), 'method_label': METHODS.get(classification.get('method'), '待分类'),
                'difficulty': classification.get('difficulty'),
                'difficulty_label': DIFFICULTIES.get(classification.get('difficulty'), '待分类'),
                'items': members, 'representative': representative, 'reason': representative['reason']})
        # One representative per group; identical originals earn only one recommendation slot.
        seen, recommended = set(), []
        domains = {}
        for group in output_groups:
            representative = group['representative']
            fingerprint = fingerprints[(representative['session_id'], representative['question_id'])]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            domains.setdefault(group['knowledge_id'], []).append(group['representative'])
        while domains and len(recommended) < limit:
            for domain in list(domains):
                if domains[domain]:
                    recommended.append(domains[domain].pop(0))
                if not domains[domain]:
                    domains.pop(domain)
                if len(recommended) >= limit:
                    break
        return dict(items=items, due_count=sum(i['due'] for i in items), total=len(items),
                    groups=output_groups, recommended=recommended, limit=limit)

    def source(self, sid, qid):
        s = self.store.get_session(sid)
        q = next((q for q in (s or {}).get('questions', []) if q['id'] == qid), None)
        if not s or not q or s.get('demo'):
            raise ValueError('原题不存在')
        if q.get('analysis', {}).get('status') != 'confirmed' or q['analysis'].get('schema_version') != 3:
            raise ValueError('请先完成原题解答与核对，再开始复习')
        return s, q

    def start(self, sid, qid):
        _, q = self.source(sid, qid)
        recent_cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        # Correcting a transcript invalidates verdicts, not the fact a learner saw help.
        with self.store.connect() as db:
            exposure_rows=db.execute('SELECT data FROM study_events WHERE user_id=? AND session_id=? AND question_id=?',
                                     (LOCAL_USER,sid,qid)).fetchall()
        exposures=(json.loads(row['data']) for row in exposure_rows)
        recently_helped = any(e['kind'] == 'viewed' and e['created_at'] > recent_cutoff for e in exposures)
        run = dict(id=uid(), session_id=sid, question_id=qid, revision=q.get('revision', 1),
                   status='ready', help_kind='assisted' if recently_helped else 'independent', created_at=now(), source_label='历史原题复习',
                   question={k: q[k] for k in ('id', 'text', 'kind', 'options', 'number') if k in q})
        with self.store.connect() as db:
            db.execute('INSERT INTO review_runs VALUES (?,?,?)', (run['id'], LOCAL_USER, json.dumps(run, ensure_ascii=False)))
        return run

    def _load_run(self, db, rid):
        row = db.execute('SELECT data FROM review_runs WHERE id=? AND user_id=?', (rid, LOCAL_USER)).fetchone()
        if not row:
            raise ValueError('复习记录不存在')
        run = json.loads(row['data'])
        _, q = self.source(run['session_id'], run['question_id'])
        if q.get('revision', 1) != run['revision']:
            raise ValueError('原题已经修订，请重新开始复习')
        if run['status'] != 'ready':
            raise ValueError('这次复习已经提交')
        return run, q

    def run_session(self, rid):
        with self.store.connect() as db:
            row = db.execute('SELECT data FROM review_runs WHERE id=? AND user_id=?', (rid, LOCAL_USER)).fetchone()
        if not row:
            raise ValueError('复习记录不存在')
        return json.loads(row['data'])['session_id']

    def mark_viewed(self, sid, qid):
        self.event(sid, qid, 'viewed', help_kind='assisted')
        # Looking at the original in another panel also contaminates an active review.
        with self.store.connect() as db:
            for row in db.execute('SELECT id,data FROM review_runs WHERE user_id=?', (LOCAL_USER,)).fetchall():
                run = json.loads(row['data'])
                if run['session_id'] == sid and run['question_id'] == qid and run['status'] == 'ready':
                    run['help_kind'] = 'assisted'
                    db.execute('UPDATE review_runs SET data=? WHERE id=?', (json.dumps(run, ensure_ascii=False), row['id']))

    def prepare_hint(self, rid):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run, q = self._load_run(db, rid)
            if run.get('hint'):
                return run, q
            run['help_kind'] = 'assisted'
            db.execute('UPDATE review_runs SET data=? WHERE id=?', (json.dumps(run, ensure_ascii=False), rid))
        self.mark_viewed(run['session_id'], run['question_id'])
        return run, q

    def cache_hint(self, run, hint):
        run['hint'] = hint
        with self.store.connect() as db:
            db.execute('UPDATE review_runs SET data=? WHERE id=?', (json.dumps(run, ensure_ascii=False), run['id']))

    def review(self, rid, answer=None):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run, q = self._load_run(db, rid)
            analysis = q['analysis']
            if answer is None:
                run['help_kind'] = 'assisted'
            else:
                validate_choice_answer(q['kind'], [Option.model_validate(o) for o in q.get('options', [])], answer)
                correct = normalized_answer(answer, q['kind']) == normalized_answer(analysis['answer'], q['kind'])
                # A successful response cannot lengthen the schedule more than once per calendar day.
                events = self.events(run['session_id'], run['question_id'])
                successful = [e for e in events if e['kind'] == 'review_answer' and e.get('correct') and e.get('help_kind') == 'independent']
                last_failure = max((i for i, e in enumerate(events) if e.get('correct') is False), default=-1)
                recent = [e for e in events[last_failure+1:] if e in successful]
                days = {local_day(e['created_at']) for e in recent}
                interval = INTERVALS[min(len(days), len(INTERVALS)-1)] if correct and run['help_kind'] == 'independent' else 1
                if local_day(now()) in days and recent:
                    due = recent[-1]['next_due_at']
                else:
                    due = later(interval)
                if not correct or run['help_kind'] != 'independent':
                    due = later(1)
                run.update(status='answered', correct=correct, submitted_answer=answer, next_due_at=due)
                event = dict(id=uid(), kind='review_answer', created_at=now(), correct=correct,
                             help_kind=run['help_kind'], next_due_at=due, review_id=rid)
                db.execute('INSERT INTO study_events VALUES (?,?,?,?,1,?)',
                           (event['id'], LOCAL_USER, run['session_id'], run['question_id'], json.dumps(event, ensure_ascii=False)))
            run.update(answer=analysis['answer'], explanation=analysis.get('explanation', ''))
            db.execute('UPDATE review_runs SET data=? WHERE id=?', (json.dumps(run, ensure_ascii=False), rid))
        # Disclosing a solution in one run affects other simultaneous runs for the same question.
        self.mark_viewed(run['session_id'], run['question_id'])
        return run
