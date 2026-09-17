"""Personal archive preferences and evidence-backed medals."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_PROFILE = {"nickname": "学习者", "signature": "", "theme": "paper",
                   "selected_medals": [], "show_stats": False}
MEDALS = {
    "first_connection": ("第一次连接", "完成第一道关联知识点的已核对题目。"),
    "next_day": ("隔日回顾", "在之后的本地日期独立完成一次原题复习。"),
    "reconnected": ("重新接通", "曾答错的原题在之后的本地日期独立答对。"),
}


def local_day(value):
    return datetime.fromisoformat(value).astimezone(SHANGHAI).date()


class Archive:
    def __init__(self, store, study):
        self.store, self.study = store, study
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS archive_profile (user_id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def profile(self):
        with self.store.connect() as db:
            row = db.execute("SELECT data FROM archive_profile WHERE user_id='local'").fetchone()
        return {**DEFAULT_PROFILE, **(json.loads(row["data"]) if row else {})}

    def medals(self):
        evidence = {key: [] for key in MEDALS}
        for session in self.store.sessions(full=True):
            if session.get("demo"):
                continue
            for q in session.get("questions", []):
                analysis = q.get("analysis", {})
                if analysis.get("schema_version") != 3 or analysis.get("status") != "confirmed":
                    continue
                revision = q.get("revision", 1)
                base = {"session_id": session["id"], "question_id": q["id"], "revision": revision}
                events = self.study.events(session["id"], q["id"])
                source = next((e for e in events if e["kind"] in ("observed_answer", "saved")), None)
                if self.study.links(session["id"], q["id"]):
                    date = (source or {"created_at": session.get("created_at", "")}).get("created_at", "")[:10]
                    evidence["first_connection"].append({**base, "date": date})
                if not source:
                    continue
                current_versions = {n['id']: n['version'] for n in self.study.library.catalog()['nodes']}
                recorded_versions = source.get('core_versions', {})
                if source.get('revision') != revision or any(current_versions.get(k) != v for k, v in recorded_versions.items()):
                    continue
                source_day = local_day(source["created_at"])
                later_reviews = [e for e in events if e["kind"] == "review_answer" and e.get("correct")
                                 and e.get("help_kind") == "independent" and local_day(e["created_at"]) > source_day]
                if later_reviews:
                    evidence["next_day"].append({**base, "date": local_day(later_reviews[0]["created_at"]).isoformat()})
                wrongs = [e for e in events if e.get('correct') is False]
                independent_successes = [e for e in events if e['kind'] == 'review_answer' and e.get('correct')
                                        and e.get('help_kind') == 'independent']
                recovery = next((success for success in independent_successes
                    if any(local_day(success['created_at']) > local_day(wrong['created_at']) for wrong in wrongs)), None)
                if recovery:
                    evidence["reconnected"].append({**base, "date": local_day(recovery["created_at"]).isoformat()})
        return [{"id": ident, "title": title, "description": description,
                 "earned": bool(evidence[ident]),
                 "earned_at": evidence[ident][0]["date"] if evidence[ident] else None,
                 "evidence": evidence[ident][:3]}
                for ident, (title, description) in MEDALS.items()]

    def get(self):
        medals = self.medals()
        earned = {m["id"] for m in medals if m["earned"]}
        profile = self.profile()
        selected = [ident for ident in profile["selected_medals"] if ident in earned][:3]
        if selected != profile["selected_medals"]:
            profile["selected_medals"] = selected
            self.save(profile, validate_earned=False)
        sessions = [s for s in self.store.sessions(full=True) if not s.get("demo")]
        questions = [(s, q) for s in sessions for q in s.get("questions", [])
                     if q.get("analysis", {}).get("schema_version") == 3
                     and q.get("analysis", {}).get("status") == "confirmed"]
        links = {link["knowledge_id"] for s, q in questions for link in self.study.links(s["id"], q["id"])}
        days = {local_day(e["created_at"]).isoformat() for s, q in questions for e in self.study.events(s["id"], q["id"])
                if e["kind"] == "review_answer"}
        return {"profile": profile, "stats": {"questions": len(questions), "linked_nodes": len(links),
                                               "review_days": len(days)}, "medals": medals}

    def save(self, profile, validate_earned=True):
        if validate_earned:
            earned = {m["id"] for m in self.medals() if m["earned"]}
            if any(ident not in earned for ident in profile["selected_medals"]):
                raise ValueError("只能选择已获得的勋章")
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO archive_profile VALUES ('local',?)",
                       (json.dumps(profile, ensure_ascii=False),))
        return self.get() if validate_earned else profile
