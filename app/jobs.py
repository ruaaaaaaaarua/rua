"""Session-owned OCR/solve jobs; network waits never hold the UI operation lock."""
import asyncio
import time

from .providers import ProviderError
from .store import message


class StudyJobs:
    def __init__(self, service):
        self.service = service
        self.active = {}
        self.tasks = {}
        self.interactions = 0
        self.background_allowed = None
        self.loop = None
        self.slots = None

    def _ensure_event(self):
        loop = asyncio.get_running_loop()
        if self.loop is not loop:
            self.loop = loop
            self.background_allowed = asyncio.Event()
            self.background_allowed.set()

    def session(self, sid):
        return self.active.get(sid)

    def interactive_start(self):
        self._ensure_event()
        self.interactions += 1
        self.background_allowed.clear()

    def interactive_end(self):
        self.interactions -= 1
        if not self.interactions:
            self.background_allowed.set()

    def start(self, session):
        self._ensure_event()
        sid = session['id']
        if sid in self.active:
            return self.active[sid]
        if session.get('demo'):
            raise ValueError('旧演示仅供历史查看，请新建学习')
        if not session['questions'] and not session['attachments']:
            raise ValueError('请先上传题目图片')
        gateway = self.service.gateway()
        parallel = getattr(gateway, 'parallel_for', lambda _: 2)('solve')
        parallel = max(1, min(8, parallel))
        # Shared across sessions, not N independent pools when opening N studies.
        if not self.active:
            self.slots = asyncio.Semaphore(parallel)
        session.update(processing=True, job_phase='recognizing', error=None,
                       job_metrics={'first_result_ms': None, 'total_ms': None})
        self.service.store.save_session(session)
        self.active[sid] = session
        self.tasks[sid] = asyncio.create_task(self._run(session, gateway, parallel))
        return session

    async def wait(self, sid):
        task = self.tasks.get(sid)
        if task:
            await asyncio.shield(task)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, s, gateway, parallel):
        started = time.monotonic()
        queue = asyncio.Queue()
        queued = set()
        errors = []
        first_id = None
        first_started = asyncio.Event()
        workers = []

        def enqueue(q):
            nonlocal first_id
            if q['id'] not in queued and not self.service.is_confirmed(q):
                if first_id is None:
                    first_id = q['id']
                queued.add(q['id'])
                queue.put_nowait(q)

        async def worker():
            while True:
                q = await queue.get()
                if q is None:
                    return
                priority = q['id'] == first_id
                if not priority:
                    await first_started.wait()
                await self.background_allowed.wait()
                async with self.slots:
                    # Recheck after waiting for a slot: user requests jump the queue.
                    await self.background_allowed.wait()
                    group = [q]
                    if priority:
                        first_started.set()
                    else:
                        while len(group) < 3 and not queue.empty():
                            extra = queue.get_nowait()
                            if extra is None:
                                queue.put_nowait(None)
                                break
                            group.append(extra)
                    await self.service.solve_group(s, group, gateway)
                    if s['job_metrics']['first_result_ms'] is None and any(self.service.is_confirmed(q) for q in group):
                        s['job_metrics']['first_result_ms'] = round((time.monotonic() - started) * 1000)
                    self.service.store.save_session(s)

        try:
            for q in s['questions']:
                enqueue(q)
            workers = [asyncio.create_task(worker()) for _ in range(parallel)]
            try:
                async for event in self.service.extract_stream(s):
                    if event['type'] == 'question':
                        enqueue(event['question'])
            except (ValueError, ProviderError) as exc:
                errors.append(str(exc))
            s['job_phase'] = 'solving'
            self.service.store.save_session(s)
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers)
            failed = [str(q.get('number') or '未编号') for q in s['questions'] if not self.service.is_confirmed(q)]
            if failed:
                errors.append('部分题目待确认，可重试：' + '、'.join(failed))
        except asyncio.CancelledError:
            errors.append('后台处理被中断，已保存结果，可重试。')
            raise
        except Exception:
            errors.append('后台处理未完成，已保存结果。请检查模型配置后重试。')
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            s.update(processing=False, job_phase=None, status='error' if errors else 'ready',
                     error='；'.join(errors) if errors else None)
            s['job_metrics']['total_ms'] = round((time.monotonic() - started) * 1000)
            if not errors and not any(m['type'] == 'overview' for m in s['messages']):
                s['messages'].append(message('assistant', '题目已整理。可以查看讲解、关联知识点，或在之后回顾原题。', 'overview'))
            self.service.store.save_session(s)
            self.active.pop(s['id'], None)
            self.tasks.pop(s['id'], None)
