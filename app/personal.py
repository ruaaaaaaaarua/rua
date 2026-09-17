"""Bounded personal projection and history retrieval."""
from .classification import group_key


def linked_ids(study, sessions):
    result = set()
    for session in sessions:
        if session.get("demo"):
            continue
        for question in session.get("questions", []):
            result.update(link["knowledge_id"] for link in study.links(session["id"], question["id"]))
    return result


def safe_node(node, visible_ids, detail=False):
    public = {key: node[key] for key in ("id", "name", "chapter_id", "status", "version", "has_content")}
    if node.get("status") != "published":
        public["has_content"] = False
    if detail:
        public["content"] = node.get("content", "") if node.get("status") == "published" else ""
        public["sources"] = node.get("sources", []) if node.get("status") == "published" else []
        public["related"] = [item for item in node.get("related", []) if item["id"] in visible_ids]
    return public


def related_history(store, study, session_id, question, limit=2):
    current_links = {link["knowledge_id"] for link in study.links(session_id, question["id"])}
    if not current_links:
        return []
    candidates = []
    current_key = group_key(question.get("classification"), study.links(session_id, question["id"]))
    for session in store.sessions(full=True):
        if session.get("demo"):
            continue
        for other in session.get("questions", []):
            if session["id"] == session_id and other["id"] == question["id"]:
                continue
            analysis = other.get("analysis", {})
            if analysis.get("schema_version") != 3 or analysis.get("status") != "confirmed":
                continue
            links = study.links(session["id"], other["id"])
            if not current_links.intersection(link["knowledge_id"] for link in links):
                continue
            events = study.events(session["id"], other["id"])
            answers = [e for e in events if e.get("correct") is not None]
            errors = [e for e in answers if e.get("correct") is False]
            successes = [e for e in answers if e.get("correct") is True]
            item = {
                "session_id": session["id"], "question_id": other["id"],
                "revision": other.get("revision", 1), "title": session.get("title", "历史学习"),
                "text": other.get("text", "")[:300],
                "state": study.summary(events)["state"],
                "earlier_errors": [{"date": e["created_at"][:10]} for e in errors[-2:]],
                "latest_improvement": ({"date": successes[-1]["created_at"][:10],
                                        "help_kind": successes[-1].get("help_kind", "unknown")}
                                       if successes else None),
                "source_url": f"/sessions/{session['id']}?question={other['id']}",
            }
            compatible = current_key is not None and current_key == group_key(other.get("classification"), links)
            candidates.append((not compatible, not bool(errors), item))
    return [item for _, _, item in sorted(candidates, key=lambda row: row[:2])[:limit]]
