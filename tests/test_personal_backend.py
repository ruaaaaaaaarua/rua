import copy
import asyncio
import json
from datetime import datetime, timezone, timedelta

from app.models import Solution
from app.knowledge import KnowledgeLibrary
import app.study as study_module
from tests.test_learning import library
from tests.test_api import setup


def classify(knowledge="psa-per-unit", *, confidence=0.9, conditions=None, difficulty="basic"):
    return {
        "knowledge_ids": [knowledge],
        "primary_knowledge_id": knowledge,
        "method": "concept",
        "variant": "direct",
        "conditions": conditions or ["target:definition", "method:direct", "boundary:same-base"],
        "difficulty": difficulty,
        "confidence": confidence,
        "reason": "tests the definition under a stated base",
    }


def test_malformed_optional_classification_does_not_destroy_valid_solution():
    parsed = Solution.model_validate({
        "answer": "B", "explanation": "ok", "classification": {"method": "invented"}
    })
    assert parsed.answer == "B"
    assert parsed.classification is None


def test_solve_classification_is_saved_and_manual_correction_is_authoritative(tmp_path):
    c, app, gateway, sid = setup(tmp_path)

    async def solve(_):
        return {"answer": "B", "explanation": "ok", "classification": classify()}

    gateway.solve = solve
    result = c.post(f"/api/sessions/{sid}/analyze").json()
    assert result["questions"][0]["classification"]["method"] == "concept"
    corrected = classify("psa-transformer", difficulty="advanced")
    response = c.patch(
        f"/api/sessions/{sid}/questions/q1/classification", json=corrected
    )
    assert response.status_code == 200
    question = response.json()["questions"][0]
    assert question["classification"]["source"] == "manual"
    assert {link["knowledge_id"] for link in question["links"]} == {"psa-transformer"}
    assert c.patch(
        f"/api/sessions/{sid}/questions/q1/classification",
        json=classify("not-a-node"),
    ).status_code == 422


def test_personal_wiki_only_exposes_linked_cards_and_no_internal_metadata(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    hidden = library(tmp_path, published=True, text="HIDDEN_PUBLISHED_MARKER")
    wiki = KnowledgeLibrary(hidden)
    app.state.service.library = wiki
    app.state.service.study.library = wiki
    ident = wiki.catalog()["nodes"][0]["id"]
    s = app.state.store.get_session(sid)
    s["questions"][0]["text"] = wiki.catalog()["nodes"][0]["name"]
    app.state.store.save_session(s)
    listing = c.get("/api/wiki").json()
    assert [node["id"] for node in listing["nodes"]] == []
    assert c.get(f"/api/wiki/{ident}").status_code == 404
    c.post(f"/api/sessions/{sid}/analyze")
    assert gateway.inputs[-1]["wiki_context"][0]["content"] == "HIDDEN_PUBLISHED_MARKER"
    c.put(f"/api/sessions/{sid}/questions/q1/links", json={"knowledge_ids": [ident]})
    listing = c.get("/api/wiki").json()
    assert [node["id"] for node in listing["nodes"]] == [ident]
    assert "content_file" not in json.dumps(listing)
    detail = c.get(f"/api/wiki/{ident}").json()
    assert detail["status"] == "published" and detail["content"] == "HIDDEN_PUBLISHED_MARKER"
    assert all(item["id"] == ident for item in detail["related"])
    assert "HIDDEN_PUBLISHED_MARKER" not in json.dumps(listing)


def test_public_session_never_exposes_unlinked_library_candidates(tmp_path):
    c, app, _, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    s["questions"][0]["candidates"] = [
        {"id": "psa-transformer", "name": "UNLINKED_TRANSFORMER", "chapter_id": "psa-components"}
    ]
    app.state.store.save_session(s)
    public = c.get(f"/api/sessions/{sid}").json()
    assert "UNLINKED_TRANSFORMER" not in json.dumps(public)
    assert public["questions"][0].get("candidates", []) == []


def test_linked_draft_is_an_unfilled_card_never_a_body(tmp_path):
    c, _, _, sid = setup(tmp_path)
    c.put(f"/api/sessions/{sid}/questions/q1/links", json={"knowledge_ids": ["psa-per-unit"]})
    detail = c.get("/api/wiki/psa-per-unit").json()
    assert detail["status"] == "draft"
    assert detail["content"] == "" and detail["has_content"] is False


def test_review_grouping_is_conservative_and_recommendations_deduplicate(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    duplicate = copy.deepcopy(s["questions"][0])
    duplicate.update(id="q2", revision=1)
    different = copy.deepcopy(s["questions"][0])
    different.update(id="q3", revision=1, text="same topic but a different condition")
    same_stem_new_options = copy.deepcopy(s["questions"][0])
    same_stem_new_options.update(id="q4", revision=1)
    same_stem_new_options["options"][1]["text"] = "a genuinely different choice"
    s["questions"].extend([duplicate, different, same_stem_new_options])
    app.state.store.save_session(s)
    outputs = {
        "q1": classify(conditions=["target:base conversion", "method:ratio", "boundary:condition-a"]),
        "q2": classify(conditions=["target:base conversion", "method:ratio", "boundary:condition-a"]),
        "q3": classify(conditions=["target:actual value", "method:ratio", "boundary:condition-a"]),
        "q4": classify(conditions=["target:limit value", "method:ratio", "boundary:condition-a"]),
    }

    async def solve(q):
        return {"answer": "B", "explanation": "ok", "classification": outputs[q["id"]]}

    gateway.solve = solve
    c.post(f"/api/sessions/{sid}/analyze")
    queue = c.get("/api/reviews?limit=5").json()
    assert queue["limit"] == 5
    assert len(queue["groups"]) == 3
    # q1/q2 are true duplicates; q4 has the same stem but different options and remains distinct.
    assert len(queue["recommended"]) == 3
    assert {item["question_id"] for item in queue["recommended"]} & {"q1", "q2"}
    assert "q4" in {item["question_id"] for item in queue["recommended"]}
    assert sum(len(group["items"]) for group in queue["groups"]) == 4
    run = c.post("/api/reviews/start", json={"session_id": sid, "question_id": "q1"}).json()
    c.post(f"/api/reviews/{run['id']}/answer", json={"answer": "B"})
    assert not any(e["kind"] == "review_answer" for e in app.state.service.study.events(sid, "q2"))


def test_review_hint_has_no_answer_and_contaminates_simultaneous_runs(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    first = app.state.service.study.start(sid, "q1")
    second = app.state.service.study.start(sid, "q1")
    result = c.post(f"/api/reviews/{first['id']}/hint").json()
    assert result["hint"] == "模型测试讲解"
    assert result["help_kind"] == "assisted"
    assert "answer" not in result and "explanation" not in result
    assert app.state.service.study.review(second["id"], "B")["help_kind"] == "assisted"
    assert gateway.inputs[-1]["hint_only"] is True


def test_review_hint_stays_sanitized_before_and_after_reveal(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    study = app.state.service.study

    cached = study.start(sid, "q1")
    first = c.post(f"/api/reviews/{cached['id']}/hint").json()
    assert "answer" not in first and "explanation" not in first
    c.post(f"/api/reviews/{cached['id']}/reveal")
    repeated = c.post(f"/api/reviews/{cached['id']}/hint").json()
    assert repeated["hint"] == first["hint"] and repeated["help_kind"] == "assisted"
    assert "answer" not in repeated and "explanation" not in repeated

    revealed = study.start(sid, "q1")
    c.post(f"/api/reviews/{revealed['id']}/reveal")
    after_reveal = c.post(f"/api/reviews/{revealed['id']}/hint").json()
    assert after_reveal["help_kind"] == "assisted"
    assert "answer" not in after_reveal and "explanation" not in after_reveal


def test_related_history_only_enters_revealed_followup_and_audit_stays_private(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    old = app.state.store.get_session(sid)
    q2 = copy.deepcopy(old["questions"][0])
    q2.update(id="q2", revision=1, text="another per unit question", revealed=True)
    old["questions"].append(q2)
    app.state.store.save_session(old)
    app.state.service.study.attach(old, q2, ["psa-per-unit"])
    app.state.service.study.event(sid, "q2", "review_answer", correct=True, help_kind="independent")
    c.post(f"/api/sessions/{sid}/analyze")
    assert "personal_history" not in json.dumps(gateway.inputs[0])
    c.post(f"/api/sessions/{sid}/messages", json={"text": "hint", "question_id": "q1"})
    assert "related_history" not in gateway.inputs[-1]
    c.post(f"/api/sessions/{sid}/questions/q1/reveal")
    response = c.post(f"/api/sessions/{sid}/messages", json={"text": "explain", "question_id": "q1"})
    assert [item["question_id"] for item in gateway.inputs[-1]["related_history"]] == ["q2"]
    public = response.json()
    assert "retrieval_audit" not in json.dumps(public)
    assert public["questions"][0]["related_history"][0]["question_id"] == "q2"


def test_archive_preferences_and_evidence_backed_medals(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    archive = c.get("/api/archive").json()
    earned = {m["id"] for m in archive["medals"] if m["earned"]}
    assert "first_connection" in earned
    assert archive["profile"] == {
        "nickname": "学习者", "signature": "", "theme": "paper",
        "selected_medals": [], "show_stats": False,
    }
    assert c.put("/api/archive", json={
        "nickname": "Grid", "signature": "steady", "theme": "blueprint",
        "selected_medals": ["first_connection"], "show_stats": True,
    }).status_code == 200
    assert c.put("/api/archive", json={
        "nickname": "Grid", "signature": "", "theme": "paper",
        "selected_medals": ["next_day"], "show_stats": False,
    }).status_code == 422
    assert "api_key" not in json.dumps(c.get("/api/archive").json())


def test_organize_is_bounded_and_does_not_write_failed_or_stale_results(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    s = app.state.store.get_session(sid)
    s["questions"][0].pop("classification", None)
    app.state.store.save_session(s)

    async def failed(_):
        raise RuntimeError("provider secret")

    gateway.solve = failed
    result = c.post("/api/reviews/organize", json={}).json()
    assert result == {"classified": 0, "remaining": 1, "failed": 1}
    assert "classification" not in app.state.store.get_session(sid)["questions"][0]


def test_organize_classifies_valid_metadata_but_rejects_revision_race(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    s = app.state.store.get_session(sid)
    s["questions"][0].pop("classification", None)
    app.state.store.save_session(s)

    async def success(_):
        return {"answer": "B", "explanation": "ok", "classification": classify()}

    gateway.solve = success
    assert c.post("/api/reviews/organize", json={}).json() == {
        "classified": 1, "remaining": 0, "failed": 0,
    }
    s = app.state.store.get_session(sid)
    s["questions"][0].pop("classification", None)
    app.state.store.save_session(s)

    async def stale(_):
        changed = app.state.store.get_session(sid)
        changed["questions"][0]["revision"] += 1
        app.state.store.save_session(changed)
        return {"answer": "B", "explanation": "ok", "classification": classify()}

    gateway.solve = stale
    assert c.post("/api/reviews/organize", json={}).json() == {
        "classified": 0, "remaining": 1, "failed": 1,
    }


def test_deleted_or_revised_history_is_not_resurrected(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    s = app.state.store.get_session(sid)
    q2 = copy.deepcopy(s["questions"][0]); q2.update(id="q2", revision=1)
    q3 = copy.deepcopy(s["questions"][0]); q3.update(id="q3", revision=1, text="still valid history")
    s["questions"].extend([q2, q3]); app.state.store.save_session(s)
    app.state.service.study.attach(s, q2, ["psa-per-unit"])
    app.state.service.study.attach(s, q3, ["psa-per-unit"])
    c.post(f"/api/sessions/{sid}/analyze")
    c.post(f"/api/sessions/{sid}/questions/q1/reveal")
    async def marker_chat(context, text, mode):
        gateway.inputs.append(copy.deepcopy(context))
        return {"content": "STALE_HISTORY_MARKER"}
    gateway.chat = marker_chat
    c.post(f"/api/sessions/{sid}/messages", json={"text": "explain", "question_id": "q1"})
    assert c.get(f"/api/sessions/{sid}").json()["questions"][0]["related_history"]
    internal = app.state.store.get_session(sid)
    assistant = [m for m in internal["messages"] if m.get("content") == "STALE_HISTORY_MARKER"][0]
    assert {item["question_id"] for item in assistant["retrieval_audit"]["history"]} == {"q2", "q3"}
    assert set(assistant["retrieval_audit"]["provider"]) == {"id", "name", "model"}
    async def dependent_chat(context, text, mode):
        gateway.inputs.append(copy.deepcopy(context))
        return {"content": "DEPENDENT_MARKER"}
    gateway.chat = dependent_chat
    c.post(f"/api/sessions/{sid}/messages", json={"text": "continue", "question_id": "q1"})
    dependent = [m for m in app.state.store.get_session(sid)["messages"]
                 if m.get("content") == "DEPENDENT_MARKER"][0]
    assert assistant["id"] in dependent["retrieval_audit"]["context_message_ids"]
    c.patch(f"/api/sessions/{sid}/questions/q2", json={"text": "revised source"})
    gateway.inputs.clear()
    c.post(f"/api/sessions/{sid}/messages", json={"text": "explain again", "question_id": "q1"})
    payload = gateway.inputs[-1]
    assert "STALE_HISTORY_MARKER" not in json.dumps(payload) and "DEPENDENT_MARKER" not in json.dumps(payload)
    assert "q2" not in json.dumps(payload)
    assert [item["question_id"] for item in payload["related_history"]] == ["q3"]
    latest = [m for m in app.state.store.get_session(sid)["messages"] if m["role"] == "assistant"][-1]
    assert latest["retrieval_audit"]["history"][0]["question_id"] == "q3"
    public = c.get(f"/api/sessions/{sid}").json()
    assert "retrieval_audit" not in json.dumps(public) and "api_key" not in json.dumps(public)


def test_review_interval_counts_shanghai_calendar_days(monkeypatch, tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    study = app.state.service.study
    study.event(sid, "q1", "review_answer", correct=True, help_kind="independent",
                next_due_at="old-due")
    with app.state.store.connect() as db:
        rows = db.execute("SELECT id,data FROM study_events WHERE session_id=?", (sid,)).fetchall()
        event_id, data = rows[-1]["id"], json.loads(rows[-1]["data"])
        data["created_at"] = "2026-09-16T15:30:00+00:00"
        db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), event_id))
    run = study.start(sid, "q1")
    monkeypatch.setattr(study_module, "now", lambda: "2026-09-16T16:30:00+00:00")
    monkeypatch.setattr(study_module, "later", lambda days, clock=None: f"due-{days}")
    assert study.review(run["id"], "B")["next_due_at"] == "due-3"


def test_same_day_review_does_not_earn_cross_day_medal_and_edit_revokes_source(tmp_path):
    c, app, _, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    study = app.state.service.study
    source = study.events(sid, "q1")[0]
    study.event(sid, "q1", "review_answer", correct=True, help_kind="independent")
    with app.state.store.connect() as db:
        rows = db.execute("SELECT id,data FROM study_events WHERE session_id=?", (sid,)).fetchall()
        data = json.loads(rows[-1]["data"])
        data["created_at"] = source["created_at"]
        db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), rows[-1]["id"]))
    medals = {m["id"]: m for m in c.get("/api/archive").json()["medals"]}
    assert medals["next_day"]["earned"] is False
    study.event(sid, "q1", "review_answer", correct=True, help_kind="independent")
    with app.state.store.connect() as db:
        rows = db.execute("SELECT id,data FROM study_events WHERE session_id=?", (sid,)).fetchall()
        data = json.loads(rows[-1]["data"])
        data["created_at"] = (datetime.fromisoformat(source["created_at"]) + timedelta(days=1)).isoformat()
        db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), rows[-1]["id"]))
    medals = {m["id"]: m for m in c.get("/api/archive").json()["medals"]}
    assert medals["next_day"]["earned"] is True and medals["reconnected"]["earned"] is True
    with app.state.store.connect() as db:
        row = db.execute("SELECT id,data FROM study_events WHERE id LIKE 'source:%'").fetchone()
        data = json.loads(row["data"]); data["core_versions"] = {"psa-per-unit": "stale-version"}
        db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), row["id"]))
    medals = {m["id"]: m for m in c.get("/api/archive").json()["medals"]}
    assert medals["first_connection"]["earned"] is False
    c.patch(f"/api/sessions/{sid}/questions/q1", json={"text": "edited"})
    medals = {m["id"]: m for m in c.get("/api/archive").json()["medals"]}
    assert medals["first_connection"]["earned"] is False


def test_progresses_after_cross_day_independent_reviews_then_steps_down_after_help(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    s = app.state.store.get_session(sid)
    harder = copy.deepcopy(s["questions"][0]); harder.update(id="q2", text="harder target")
    s["questions"].append(harder); app.state.store.save_session(s)
    async def solve(q):
        return {"answer": "B", "explanation": "ok", "classification": classify(
            difficulty="basic" if q["id"] == "q1" else "advanced")}
    gateway.solve = solve
    c.post(f"/api/sessions/{sid}/analyze")
    study = app.state.service.study
    for stamp in ("2026-09-14T02:00:00+00:00", "2026-09-15T02:00:00+00:00"):
        event = study.event(sid, "q1", "review_answer", correct=True, help_kind="independent")
        with app.state.store.connect() as db:
            row = db.execute("SELECT data FROM study_events WHERE id=?", (event["id"],)).fetchone()
            data = json.loads(row["data"]); data["created_at"] = stamp
            db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), event["id"]))
    assert c.get("/api/reviews").json()["groups"][0]["representative"]["question_id"] == "q2"
    study.event(sid, "q2", "review_answer", correct=True, help_kind="assisted")
    assert c.get("/api/reviews").json()["groups"][0]["representative"]["question_id"] == "q1"


def test_reconnected_medal_accepts_later_review_error_after_correct_source(tmp_path):
    c, app, gateway, sid = setup(tmp_path)
    async def correct_source(_):
        return {"answer": "A", "explanation": "ok"}
    gateway.solve = correct_source
    c.post(f"/api/sessions/{sid}/analyze")
    study = app.state.service.study
    source_time = datetime.fromisoformat(study.events(sid, "q1")[0]["created_at"])
    wrong = study.event(sid, "q1", "review_answer", correct=False, help_kind="independent")
    recovered = study.event(sid, "q1", "review_answer", correct=True, help_kind="independent")
    with app.state.store.connect() as db:
        for event, stamp in ((wrong, (source_time + timedelta(days=1)).isoformat()),
                             (recovered, (source_time + timedelta(days=2)).isoformat())):
            row = db.execute("SELECT data FROM study_events WHERE id=?", (event["id"],)).fetchone()
            data = json.loads(row["data"]); data["created_at"] = stamp
            db.execute("UPDATE study_events SET data=? WHERE id=?", (json.dumps(data), event["id"]))
    medals = {m["id"]: m for m in c.get("/api/archive").json()["medals"]}
    assert medals["reconnected"]["earned"] is True


def test_organize_blocks_a_new_background_job_while_model_is_in_flight(tmp_path):
    import httpx
    c, app, gateway, sid = setup(tmp_path)
    c.post(f"/api/sessions/{sid}/analyze")
    s = app.state.store.get_session(sid); s["questions"][0].pop("classification", None)
    app.state.store.save_session(s)

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def slow(_):
            started.set(); await release.wait()
            return {"answer": "B", "explanation": "ok", "classification": classify()}
        gateway.solve = slow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            pending = asyncio.create_task(client.post("/api/reviews/organize", json={}))
            await started.wait()
            blocked = await client.post(f"/api/sessions/{sid}/process")
            blocked_chat = await client.post(f"/api/sessions/{sid}/messages", json={"text":"concurrent"})
            release.set(); finished = await pending
        assert blocked.status_code == 409 and blocked_chat.status_code == 409
        assert finished.json()["classified"] == 1
    asyncio.run(scenario())
