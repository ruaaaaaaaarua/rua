# 电网学习助手 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for bounded components and inline execution for integration. User has authorized implementation; no further design approval gate.

**Goal:** Implement v2 as a local, persistent learning workspace with real configurable AI calls.
**Architecture:** FastAPI serves a built React workspace and SQLite data. A provider service owns all model calls; a learning service owns persistence and evidence. Keys are private local config, never returned to the browser.
**Tech Stack:** Python 3.9+, FastAPI/Pydantic, sqlite3, httpx, React/Vite, pytest.

## Global Constraints
- Local only; bind 127.0.0.1. No hosted Sites deployment: explicit local data/backend requirement overrides cloud starter/storage.
- Whole-page feedback; correct questions get one knowledge sentence; uncertain questions get concise distinction.
- Explicit action required for variants, prerequisite or depth tests. No automatic quizzes.
- Knowledge based on valid attempts, no direct mastery edits; corrections/deletion recompute evidence.
- Independent solve sees no user answer. Verifier sees no generated answer until comparison.
- Task-specific manual model mappings, bounded retries, no automatic model routing.
- Document authentic limitations when no live credentials are available; demo clearly labeled and isolated.

## API contract (JSON, /api prefix)
- GET /sessions -> [{id,title,created_at,updated_at,status,mode,demo}]
- POST /sessions {title?,mode?} -> session detail
- GET /sessions/{id} -> {id,title,created_at,updated_at,status,mode,demo,messages:[],questions:[],attachments:[],error?}
- PATCH /sessions/{id} {title?,mode?} -> detail. mode='direct'|'hint'
- DELETE /sessions/{id}?delete_evidence=false -> {ok:true}
- POST /sessions/{id}/upload multipart files[] (field `files`) -> detail; uploads stored then process via /analyze
- POST /sessions/{id}/analyze {} -> detail; synchronous request, persisted status, retains extraction for retry
- POST /sessions/{id}/messages {text,question_id?} -> detail
- PATCH /sessions/{id}/questions/{qid} {text?,options?,user_answer?,reasoning?,confidence?,kind?} -> detail, clears analysis, user triggers analyze
- POST /sessions/{id}/questions/{qid}/reveal {} -> detail
- POST /sessions/{id}/train {question_id?,knowledge_id?,purpose:'variant'|'verify'|'prerequisite'|'depth'} -> detail (adds message with quiz)
- POST /sessions/{id}/quiz/{quizid}/answer {answer,reasoning?} -> detail
- POST /sessions/{id}/questions/{qid}/recheck {text} -> detail, reevaluate with user reference not blind override
- POST /sessions/{id}/reference {text} -> detail
- GET /knowledge -> [{id,subject,chapter,name,state,summary,last_verified,evidence_count,evidence:[],history:[]}]
- GET /settings -> {profiles:[{id,name,base_url,model,has_key}],tasks:{vision,solve,chat,generate,verify},mode:'direct'|'hint'}
- PUT /settings same structure, profile api_key optional empty preserves, remove_key true deletes; response redacted
- POST /settings/test {profile_id} -> {ok,message}; tests real configured provider
- POST /demo -> detail with explicit demonstration metadata; no fake live inference.
- GET /health -> {ok:true}

Session questions: {id,number,kind:'single'|'multiple'|'judge',text,options:[{key,text}],user_answer,reasoning,confidence:'certain'|'unsure'|'guess'|'unknown',subject,chapter,knowledge,attachment_id?,recognition_note?,analysis:{correct:bool|null,answer?,knowledge_point,diagnosis,distinction,hint,explanation?,reasoning_ok:bool|null,error_type,status:'confirmed'|'pending',source,knowledge_id?},revealed:bool}
Message: {id,role:'user'|'assistant'|'system',content,created_at,type:'text'|'overview'|'quiz',quiz?:{id,purpose,question:{number?,kind,text,options},status:'ready'|'answered',answer?,correct?,feedback?,reasoning?}}
Attachment: {id,name,url,mime}
Hint mode API redacts analysis.answer and explanation until reveal. Quiz correct answer is never included before submission.

## Task 1 — Domain and persistence (root)
Files: app/store.py, app/service.py, app/main.py, tests/test_learning.py.
- [ ] Write failing tests for multi-answer order, pending not updating evidence, hint answer redaction, corrected evidence retraction, deletion modes, isolated demo.
- [ ] Run `.venv/bin/python -m pytest tests/test_learning.py -q` and record missing behavior.
- [ ] Implement SQLite records, evidence projection, whole-page workflow and endpoints per contract.
- [ ] Run tests; inspect actual persistent data and failure resume.

## Task 2 — Provider boundary (delegated bounded task)
Files: app/models.py, app/providers.py, app/prompts.py, tests/test_providers.py.
- [ ] Test with httpx mock transport: role redaction, retries, JSON schema failure, answer-free solve/verifier, key redaction, task routing.
- [ ] Implement ModelGateway(settings:dict, transport=None) with async extract(images), solve(question), diagnose(question,solution,history), chat(context,text,mode), generate(context,purpose), verify(question); return validated dictionaries.
- [ ] Use OpenAI-compatible /chat/completions HTTP, optional JSON format, 120s timeout and maximum 2 calls on transient failure; no error bodies exposing secrets.
- [ ] Schema failures raise ProviderError with user-safe message. Report test results.

## Task 3 — Web workspace (delegated bounded task)
Files: web/package.json, web/index.html, web/src/*, web/vite.config.*.
- [ ] Build polished Chinese desktop workspace: sidebar conversations, centered welcome/composer, overview cards, right question panel; no stock landing page.
- [ ] Connect all contract endpoints. Include settings with per-task profile selection, upload retry, editing, references, knowledge evidence, deletion scope, selected quiz answers and explanations.
- [ ] Explicit demo entry, empty states and busy/error states, responsive layouts and accessible controls.
- [ ] Run production build and fix compilation failures; root verifies integrated endpoints.

## Task 4 — Integration and review (root + reviewer)
Files: README.md, requirements.txt, start.command, .gitignore, tests/test_api.py.
- [ ] Add endpoint integration tests covering workflow with deterministic injected gateway, not fabricated real AI.
- [ ] Install dependencies, build frontend, run full tests, exercise server /health and index over HTTP.
- [ ] Review app for credential exposure, answer leakage, accidental automatic training, evidence continuity.
- [ ] Fix findings and rerun affected checks. Document start instructions, backup paths, API configuration and unsupported provider dialects.
- [ ] Open final localhost workspace and report verified scope and live-AI validation limitation.
