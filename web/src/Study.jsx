import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  FileImage,
  Link2,
  Lightbulb,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Upload,
  X,
} from "lucide-react";
import { api } from "./api.js";
import {
  answerText,
  analysisStage,
  buildClassification,
  toggleAnswer,
} from "./domain.js";
import { Empty, Loading, Markdown, Modal, Sources, dateText } from "./ui.jsx";

export const IMAGE_TYPES =
  "image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif";
export function appendMissingOption(draft) {
  const options = draft.options || [];
  if (options.length >= 8) return draft;
  const used = new Set(options.map((option) => option.key));
  const key = "ABCDEFGH".split("").find((candidate) => !used.has(candidate));
  return key ? { ...draft, options: [...options, { key, text: "" }] } : draft;
}

export function buildQuestionPatch(draft, completenessConfirmed = false) {
  return {
    text: draft.text,
    kind: draft.kind,
    options: draft.options,
    user_answer: draft.user_answer,
    ...(completenessConfirmed ? { completeness_confirmed: true } : {}),
  };
}
export function UploadButton({ onFiles, busy, large = false }) {
  const input = useRef();
  return (
    <>
      <button
        className={large ? "upload-zone" : "primary"}
        disabled={busy}
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!busy && e.dataTransfer.files.length)
            onFiles([...e.dataTransfer.files]);
        }}
      >
        <Upload size={large ? 25 : 16} />
        {large ? (
          <>
            <strong>把一道题，变成一次理解</strong>
            <span>点击上传或拖入题目图片</span>
            <small>HEIC / JPG / PNG / WebP · 支持多张</small>
          </>
        ) : (
          "上传题目"
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept={IMAGE_TYPES}
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files.length) onFiles([...e.target.files]);
          e.target.value = "";
        }}
      />
    </>
  );
}

export function Dashboard({
  sessions,
  wiki,
  reviews,
  busy,
  onFiles,
  onSession,
  onChapter,
  onReviews,
}) {
  return (
    <div className="dashboard page">
      <section className="welcome-heading">
        <div className="eyebrow">
          <span />
          YOUR LEARNING SPACE
        </div>
        <h1>
          让每一次学习，
          <br />
          <em>都有迹可循。</em>
        </h1>
        <p>从一道题出发，连接知识，留一点时间给复习。</p>
      </section>
      <div className="dashboard-primary">
        <UploadButton onFiles={onFiles} busy={busy} large />
        <section className="review-teaser">
          <div className="eyebrow">回到学过的地方</div>
          <div className="review-teaser-symbol">↺</div>
          <h2>
            {reviews?.due_count
              ? `今天有 ${reviews.due_count} 道题待复习`
              : "给记忆一点回响"}
          </h2>
          <p>
            {reviews?.total
              ? `共 ${reviews.total} 道历史原题，${reviews.due_count ? "按计划重访，看看这次的回答。" : "也可以提前开始复习。"}`
              : "完成作答后，历史原题会在这里等你再试一次。"}
          </p>
          <button className="text-link" onClick={onReviews}>
            查看复习安排 <ArrowRight size={15} />
          </button>
        </section>
      </div>
      {sessions.length > 0 && (
        <section className="dashboard-section">
          <div className="section-top">
            <h2>接着上次的思路</h2>
            <span className="muted small">最近学习</span>
          </div>
          <div className="recent-cards">
            {sessions.slice(0, 3).map((s) => (
              <button
                className="recent-card"
                key={s.id}
                onClick={() => onSession(s.id)}
              >
                <span className="card-icon">
                  <FileImage size={18} />
                </span>
                <strong>{s.title || "未命名学习"}</strong>
                <span className="muted small">{dateText(s.updated_at)}</span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        </section>
      )}
      <section className="dashboard-section">
        <div className="section-top">
          <div>
            <h2>一张知识地图，慢慢填满</h2>
            <p className="muted small">
              电力系统分析 · 从章节找到概念，再回到题目
            </p>
          </div>
          <button className="text-link" onClick={() => onChapter("all")}>
            浏览知识库 <ArrowRight size={15} />
          </button>
        </div>
        <div className="chapter-previews">
          {wiki?.chapters
            ?.filter((c) =>
              (wiki.nodes || []).some((n) => n.chapter_id === c.id),
            )
            .slice(0, 4)
            .map((c, i) => (
              <button
                className="chapter-preview"
                key={c.id}
                onClick={() => onChapter(c.id)}
              >
                <span className="chapter-number">0{i + 1}</span>
                <BookOpen size={18} strokeWidth={1.4} />
                <h3>{c.name}</h3>
                <span className="muted small">
                  {
                    (wiki.nodes || []).filter((n) => n.chapter_id === c.id)
                      .length
                  }{" "}
                  个知识节点
                </span>
                <ArrowRight size={15} />
              </button>
            ))}
        </div>
        {wiki && !wiki.nodes?.length && (
          <p className="catalog-note">
            <span className="status-dot" />
            上传题目照片并完成分析后，与题目相连的知识点会出现在这里。
          </p>
        )}
      </section>
      <footer className="dashboard-foot">
        积累理解，不止积累答案。<span>电力系统分析学习工作台</span>
      </footer>
    </div>
  );
}

export function AnswerChoices({
  question,
  value,
  onChange,
  disabled,
  readOnly = false,
}) {
  const options = question.options?.length
    ? question.options
    : question.kind === "judge"
      ? [
          { key: "正确", text: "正确" },
          { key: "错误", text: "错误" },
        ]
      : [];
  const selected = (
    question.kind === "multiple" && /^[A-Z]+$/.test(answerText(value))
      ? answerText(value).split("")
      : answerText(value).split(/[,，、\s]+/)
  ).filter(Boolean);
  return options.length ? (
    <div
      className="answer-options"
      role="group"
      aria-label={readOnly ? "图片选项与作答" : "选择答案"}
    >
      {options.map((o) =>
        readOnly ? (
          <div
            key={o.key}
            className={`answer-option static-option ${selected.includes(o.key) ? "chosen" : ""}`}
          >
            <span className="option-key">{o.key}</span>
            <Markdown>{o.text}</Markdown>
            {selected.includes(o.key) && <span className="small">原作答</span>}
          </div>
        ) : (
          <button
            key={o.key}
            disabled={disabled}
            aria-pressed={selected.includes(o.key)}
            className={`answer-option ${selected.includes(o.key) ? "chosen" : ""}`}
            onClick={() => onChange(toggleAnswer(value, o.key, question.kind))}
          >
            <span className="option-key">{o.key}</span>
            <Markdown>{o.text}</Markdown>
            {selected.includes(o.key) && <Check size={16} />}
          </button>
        ),
      )}
    </div>
  ) : (
    <label>
      你的答案
      <input
        disabled={disabled}
        value={answerText(value)}
        onChange={(e) => onChange(e.target.value)}
        placeholder="输入答案"
      />
    </label>
  );
}

function LinkPicker({ question, wiki, onClose, onSave, busy }) {
  const [ids, setIds] = useState(
      (question.links || []).map((l) => l.knowledge_id),
    ),
    [query, setQuery] = useState("");
  const nodes = (wiki?.nodes || []).filter((n) =>
    `${n.name} ${(n.aliases || []).join(" ")}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <Modal title="关联知识节点" onClose={onClose}>
      <div className="modal-body">
        <p className="muted">可选择多个已有节点。取消全部勾选可解除关联。</p>
        <input
          aria-label="搜索关联节点"
          placeholder="搜索知识节点…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="link-picker-list">
          {nodes.map((n) => (
            <label className="link-choice" key={n.id}>
              <input
                type="checkbox"
                checked={ids.includes(n.id)}
                onChange={(e) =>
                  setIds((prev) =>
                    e.target.checked
                      ? [...prev, n.id]
                      : prev.filter((id) => id !== n.id),
                  )
                }
              />
              <span>
                <strong>{n.name}</strong>
                <small>
                  {wiki.chapters.find((c) => c.id === n.chapter_id)?.name}
                </small>
              </span>
              <span className="pill neutral">
                {n.has_content ? "有正文" : "待填充"}
              </span>
            </label>
          ))}
          {!nodes.length && (
            <Empty title="没有匹配节点">试试其他关键词。</Empty>
          )}
        </div>
      </div>
      <footer className="modal-footer">
        <span className="muted small">已选 {ids.length} 项</span>
        <button className="secondary" onClick={() => setIds([])}>
          清空
        </button>
        <button className="primary" disabled={busy} onClick={() => onSave(ids)}>
          保存关联
        </button>
      </footer>
    </Modal>
  );
}

function ClassificationEditor({
  question,
  sessionId,
  wiki,
  busy,
  act,
  onClose,
}) {
  const current = question.classification || {};
  const condition = (prefix) =>
    (current.conditions || [])
      .find((value) => value.startsWith(`${prefix}:`))
      ?.slice(prefix.length + 1) || "";
  const initialId =
    current.primary_knowledge_id ||
    question.links?.[0]?.knowledge_id ||
    wiki?.nodes?.[0]?.id ||
    "";
  const [taxonomy, setTaxonomy] = useState(null);
  const [draft, setDraft] = useState({
    knowledge_ids: current.knowledge_ids || (initialId ? [initialId] : []),
    primary_knowledge_id: initialId,
    method: current.method || "concept",
    variant: current.variant || "direct",
    difficulty: current.difficulty || "basic",
    target: condition("target"),
    methodCondition: condition("method"),
    boundary: condition("boundary"),
    reason: current.reason || "",
  });
  useEffect(() => {
    api
      .reviewTaxonomy()
      .then(setTaxonomy)
      .catch(() =>
        setTaxonomy({ methods: [], variants: [], difficulties: [] }),
      );
  }, []);
  const save = () => {
    const allowed = {
      knowledgeIds: new Set((wiki?.nodes || []).map((node) => node.id)),
      methods: new Set((taxonomy?.methods || []).map((item) => item.id)),
      variants: new Set((taxonomy?.variants || []).map((item) => item.id)),
      difficulties: new Set(
        (taxonomy?.difficulties || []).map((item) => item.id),
      ),
    };
    let payload;
    try {
      payload = buildClassification(draft, allowed);
    } catch (error) {
      window.alert(error.message);
      return;
    }
    act(() => api.classifyQuestion(sessionId, question.id, payload), onClose);
  };
  return (
    <Modal title="纠正题目分类" onClose={onClose}>
      <div className="modal-body classification-editor">
        <p className="muted">
          只分类题目要求，不推断你的错因。人工确认将保留为可修改的分类。
        </p>
        <label>
          主知识点
          <select
            value={draft.primary_knowledge_id}
            onChange={(e) =>
              setDraft({
                ...draft,
                primary_knowledge_id: e.target.value,
                knowledge_ids: [e.target.value],
              })
            }
          >
            <option value="">请选择</option>
            {(wiki?.nodes || []).map((node) => (
              <option key={node.id} value={node.id}>
                {node.name}
              </option>
            ))}
          </select>
        </label>
        <div className="classification-grid">
          <label>
            方法
            <select
              value={draft.method}
              onChange={(e) => setDraft({ ...draft, method: e.target.value })}
            >
              {(taxonomy?.methods || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            变体
            <select
              value={draft.variant}
              onChange={(e) => setDraft({ ...draft, variant: e.target.value })}
            >
              {(taxonomy?.variants || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            估计难度
            <select
              value={draft.difficulty}
              onChange={(e) =>
                setDraft({ ...draft, difficulty: e.target.value })
              }
            >
              {(taxonomy?.difficulties || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {[
          ["target", "目标"],
          ["methodCondition", "方法条件"],
          ["boundary", "边界条件"],
          ["reason", "分类理由"],
        ].map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              value={draft[key]}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <footer className="modal-footer">
        <button className="secondary" onClick={onClose}>
          取消
        </button>
        <button className="primary" disabled={busy || !taxonomy} onClick={save}>
          保存分类
        </button>
      </footer>
    </Modal>
  );
}

function QuestionCard({
  question: q,
  session,
  selected,
  onSelect,
  busy,
  run,
  update,
  wiki,
  onKnowledge,
  onExpand,
  onOpenQuestion,
}) {
  const [editing, setEditing] = useState(false),
    [draft, setDraft] = useState(q),
    [answer, setAnswer] = useState(""),
    [reference, setReference] = useState(""),
    [linking, setLinking] = useState(false),
    [classifying, setClassifying] = useState(false),
    [retrying, setRetrying] = useState(false),
    [revealed, setRevealed] = useState(false),
    [completenessConfirmed, setCompletenessConfirmed] = useState(false);
  const hasAnswer = !!answerText(q.user_answer).trim();
  const confirmed = q.analysis?.status === "confirmed" && !q.legacy;
  const structuralDisabled = busy || session.processing;
  const actionDisabled = busy || !confirmed;
  const answering = !hasAnswer || retrying;
  useEffect(() => {
    setDraft(q);
    setCompletenessConfirmed(false);
  }, [q]);
  const source = session.attachments?.find((a) => a.id === q.attachment_id);
  const act = (action, callback) =>
    run(action, (value) => {
      update(value);
      callback?.();
    });
  return (
    <article className={`question-card ${selected ? "selected" : ""}`}>
      <header className="question-head">
        <button className="question-number" onClick={onSelect}>
          题目 {String(q.number || 1).padStart(2, "0")}
        </button>
        <span className="pill neutral">
          {{ single: "单选题", multiple: "多选题", judge: "判断题" }[q.kind] ||
            "题目"}
        </span>
        <span className="question-status">
          {q.analysis
            ? q.analysis.status === "pending"
              ? "答案待确认"
              : "解析已就绪"
            : "待解答"}
        </span>
        <button
          className="icon-button"
          aria-label="编辑识别内容"
          disabled={structuralDisabled}
          onClick={() => {
            if (!editing) setCompletenessConfirmed(false);
            setEditing(!editing);
          }}
        >
          <Pencil size={15} />
        </button>
      </header>
      {q.legacy && (
        <p className="notice">这是旧版记录，请重新解答后加入新的复习安排。</p>
      )}
      {q.recognition_note && (
        <p className="notice">识别提示：{q.recognition_note}</p>
      )}
      {q.incomplete && (
        <p className="notice error">
          识别内容可能不完整：请对照原图补全题干、全部选项及必要图示。
        </p>
      )}
      {q.scope_note && <p className="notice">{q.scope_note}</p>}
      {editing ? (
        <div className="question-editor">
          <label>
            题干
            <textarea
              rows={4}
              value={draft.text || ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, text: e.target.value }))
              }
            />
          </label>
          <label>
            题型
            <select
              value={draft.kind}
              onChange={(e) =>
                setDraft((d) => ({ ...d, kind: e.target.value }))
              }
            >
              <option value="single">单选题</option>
              <option value="multiple">多选题</option>
              <option value="judge">判断题</option>
            </select>
          </label>
          {draft.options?.map((o, i) => (
            <label key={o.key}>
              选项 {o.key}
              <input
                value={o.text}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    options: d.options.map((x, j) =>
                      j === i ? { ...x, text: e.target.value } : x,
                    ),
                  }))
                }
              />
            </label>
          ))}
          {q.incomplete && (draft.options?.length || 0) < 8 && (
            <button
              type="button"
              className="secondary compact"
              onClick={() => setDraft(appendMissingOption)}
            >
              <Plus size={13} />
              补充选项
            </button>
          )}
          <label>
            图片中的作答
            <input
              value={answerText(draft.user_answer)}
              onChange={(e) =>
                setDraft((d) => ({ ...d, user_answer: e.target.value }))
              }
            />
          </label>
          <div className="actions">
            {q.incomplete && (
              <label className="completeness-check">
                <input
                  type="checkbox"
                  checked={completenessConfirmed}
                  onChange={(event) =>
                    setCompletenessConfirmed(event.target.checked)
                  }
                />
                我已根据原图补全题干、全部选项及必要图示
              </label>
            )}
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                act(
                  () =>
                    api.patchQuestion(
                      session.id,
                      q.id,
                      buildQuestionPatch(draft, completenessConfirmed),
                    ),
                  () => {
                    setEditing(false);
                    setRevealed(false);
                  },
                )
              }
            >
              保存修改
            </button>
            <button
              className="secondary"
              onClick={() => {
                setDraft(q);
                setEditing(false);
              }}
            >
              取消
            </button>
            {source?.url && (
              <a
                className="text-link"
                href={source.url}
                target="_blank"
                rel="noreferrer"
              >
                查看原图
              </a>
            )}
          </div>
          <p className="muted small">保存后原解析失效，可重新解答。</p>
        </div>
      ) : (
        <>
          <div className="question-text">
            <Markdown>{q.text}</Markdown>
          </div>
          <AnswerChoices
            question={q}
            value={answering ? answer : q.user_answer}
            onChange={setAnswer}
            disabled={busy}
            readOnly={!answering}
          />
          {q.user_answer && (
            <p className="muted small">
              照片中的作答：{answerText(q.user_answer)} · 上传前的帮助情况未知
            </p>
          )}
          {hasAnswer && (
            <div
              className={`answer-verdict ${q.analysis?.correct === true ? "is-correct" : q.analysis?.correct === false ? "is-wrong" : ""}`}
              role="status"
            >
              <strong>
                {q.legacy
                  ? "旧版判定待重新核对"
                  : q.analysis?.correct === true
                    ? "答对了"
                    : q.analysis?.correct === false
                      ? "答错了"
                      : q.analysis?.status === "pending"
                        ? "待确认"
                        : "正在核对作答…"}
              </strong>
              <span>
                你的作答：{answerText(q.user_answer)}
                {q.analysis?.correct != null && !q.legacy
                  ? " · 根据当前模型解答核对，可补充依据复核"
                  : ""}
              </span>
            </div>
          )}
        </>
      )}
      <div className="question-links">
        {q.links?.map((l) => (
          <button
            className="concept-link"
            key={l.knowledge_id}
            onClick={() => onKnowledge(l.knowledge_id)}
          >
            <BookOpen size={12} />
            {l.name}
          </button>
        ))}
        <button
          className="link-edit"
          disabled={structuralDisabled}
          onClick={() => setLinking(true)}
        >
          <Link2 size={13} />
          {q.links?.length ? "编辑关联" : "关联知识"}
        </button>
        <button
          className="link-edit"
          disabled={structuralDisabled}
          onClick={() => setClassifying(true)}
        >
          <Pencil size={13} />
          {q.classification ? "纠正分类" : "手动分类"}
        </button>
        {q.classification && (
          <span className="muted small">
            难度与理由为估计，不是权威判定 · {q.classification.reason}
          </span>
        )}
      </div>
      {!editing && (
        <div className="question-actions">
          {answering && (
            <button
              className="primary compact"
              disabled={
                busy ||
                !answer.trim() ||
                q.analysis?.status !== "confirmed" ||
                q.legacy
              }
              onClick={() =>
                act(
                  () => api.retryQuestion(session.id, q.id, { answer }),
                  () => {
                    setAnswer("");
                    setRetrying(false);
                    setRevealed(true);
                  },
                )
              }
            >
              提交作答
            </button>
          )}
          {hasAnswer && !retrying && (
            <button
              className="text-link"
              disabled={actionDisabled}
              onClick={() => setRetrying(true)}
            >
              我再试一次
            </button>
          )}
          {retrying && (
            <button
              className="text-link"
              onClick={() => {
                setRetrying(false);
                setAnswer("");
              }}
            >
              取消重答
            </button>
          )}
          {q.analysis?.status === "confirmed" && !q.legacy ? (
            <button
              className="secondary compact"
              disabled={busy}
              onClick={() =>
                revealed
                  ? setRevealed(false)
                  : act(
                      () => api.reveal(session.id, q.id),
                      () => setRevealed(true),
                    )
              }
            >
              <ChevronDown size={14} />
              {revealed ? "收起解析" : "查看解析"}
            </button>
          ) : (
            <button
              className="secondary compact"
              disabled={busy || session.processing}
              onClick={() => act(() => api.process(session.id))}
            >
              <RefreshCw size={14} />
              解答题目
            </button>
          )}
          <button
            className="secondary compact"
            disabled={actionDisabled}
            onClick={() => {
              onSelect();
              act(() => api.hint(session.id, q.id));
            }}
          >
            <Lightbulb size={14} />
            {session.messages?.some(
              (m) =>
                m.type === "hint" &&
                m.question_id === q.id &&
                m.question_revision === (q.revision || 1),
            )
              ? "打开已有提示"
              : "给我一点提示"}
          </button>
          <button
            className="text-link"
            disabled={actionDisabled}
            onClick={onSelect}
          >
            <MessageSquare size={14} />
            追问这道题
          </button>
        </div>
      )}
      {revealed && q.analysis && (
        <section className="solution">
          <div className="solution-heading">
            <strong>
              参考答案：{answerText(q.analysis.answer) || "暂未确认"}
            </strong>
            {q.analysis.correct != null && (
              <span
                className={`pill ${q.analysis.correct ? "success" : "warning"}`}
              >
                {q.analysis.correct ? "原记录答对" : "原记录答错"}
              </span>
            )}
          </div>
          <Markdown>{q.analysis.explanation}</Markdown>
          <button
            className="text-link"
            disabled={busy}
            onClick={() => {
              onSelect();
              onExpand?.();
            }}
          >
            <MessageSquare size={14} />
            请详细展开这份解析
          </button>
          <Sources
            citations={q.analysis.citations}
            knowledgeStatus={q.analysis.knowledge_status}
            source={q.analysis.source}
            onKnowledge={onKnowledge}
            linkedKnowledgeIds={new Set((wiki?.nodes || []).map((n) => n.id))}
          />
          {q.related_history?.length > 0 && (
            <div className="related-history">
              <span className="eyebrow">相关的个人学习记录</span>
              {q.related_history.slice(0, 2).map((item) => (
                <button
                  key={`${item.session_id}-${item.question_id}-${item.revision}`}
                  className="linked-question"
                  onClick={() =>
                    onOpenQuestion?.(item.session_id, item.question_id)
                  }
                >
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.state}</small>
                  </span>
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          )}
          <details className="recheck">
            <summary>对答案有疑问？补充依据复核</summary>
            <textarea
              aria-label="复核依据"
              rows={2}
              disabled={structuralDisabled}
              value={reference}
              placeholder="粘贴教材原文、参考答案或你的疑问"
              onChange={(e) => setReference(e.target.value)}
            />
            <button
              className="secondary compact"
              disabled={structuralDisabled || !reference.trim()}
              onClick={() =>
                act(
                  () => api.recheck(session.id, q.id, reference),
                  () => setReference(""),
                )
              }
            >
              <RefreshCw size={13} />
              重新核对
            </button>
          </details>
        </section>
      )}
      {linking && (
        <LinkPicker
          question={q}
          wiki={wiki}
          busy={busy}
          onClose={() => setLinking(false)}
          onSave={(ids) =>
            act(
              () => api.linkQuestion(session.id, q.id, ids),
              () => setLinking(false),
            )
          }
        />
      )}
      {classifying && (
        <ClassificationEditor
          question={q}
          sessionId={session.id}
          wiki={wiki}
          busy={busy}
          act={act}
          onClose={() => setClassifying(false)}
        />
      )}
    </article>
  );
}

export function Conversation({
  session,
  selected,
  knowledge,
  busy,
  onSend,
  onKnowledge,
  onClear,
  linkedKnowledgeIds,
}) {
  const [text, setText] = useState(""),
    tail = useRef();
  const messages = (session?.messages || []).filter(
    (m) =>
      m.type !== "quiz" &&
      (m.question_id || null) === (selected?.id || null) &&
      (!selected || m.question_revision === (selected.revision || 1)),
  );
  const unavailable = selected && selected.analysis?.status !== "confirmed";
  useEffect(() => {
    tail.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages.length, selected?.id]);
  useEffect(() => {
    setText("");
  }, [selected?.id]);
  const send = async () => {
    if (!busy && !unavailable && text.trim() && (await onSend(text.trim())))
      setText("");
  };
  return (
    <section className="conversation">
      <header>
        <span className="assistant-mark">✳</span>
        <div>
          <h2>一起想明白</h2>
          <p>
            {selected
              ? "本题讨论独立保存，不带入其他题的聊天"
              : "本次学习的公共讨论"}
          </p>
        </div>
      </header>
      {(selected || knowledge) && (
        <div className="chat-context">
          <BookOpen size={13} />
          <span>
            {knowledge ? knowledge.name : `正在追问第 ${selected.number} 题`}
          </span>
          <button aria-label="取消追问上下文" onClick={onClear}>
            <X size={13} />
          </button>
        </div>
      )}
      <div className="messages">
        {!messages.length && (
          <div className="chat-empty">
            <MessageSquare size={23} strokeWidth={1.3} />
            <p>
              {knowledge
                ? `可以从“${knowledge.name}是什么”开始。`
                : "哪里还没想通？\n选一道题，或直接开始提问。"}
            </p>
          </div>
        )}
        {messages.map((m) => (
          <article className={`message ${m.role}`} key={m.id}>
            <span className="message-role">
              {m.role === "user"
                ? "你"
                : m.role === "assistant"
                  ? "学习助手"
                  : "学习记录"}
            </span>
            {m.hint_only && m.role === "assistant" && (
              <span className="pill neutral">思考提示 · 属于辅助学习</span>
            )}
            <Markdown>{m.content}</Markdown>
            {m.role === "assistant" && m.knowledge_status && (
              <Sources
                citations={m.citations}
                knowledgeStatus={m.knowledge_status}
                onKnowledge={onKnowledge}
                linkedKnowledgeIds={linkedKnowledgeIds}
              />
            )}
          </article>
        ))}
        <div ref={tail} />
      </div>
      <div className="chat-composer">
        <textarea
          aria-label="学习追问"
          rows={3}
          placeholder="写下你的问题…"
          disabled={unavailable}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div>
          <span>Enter 发送 · Shift + Enter 换行</span>
          <button
            className="send-button"
            aria-label="发送问题"
            disabled={busy || unavailable || !text.trim()}
            onClick={send}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}

export default function Study({
  session,
  selectedId,
  setSelectedId,
  wiki,
  busy,
  run,
  update,
  onFiles,
  onKnowledge,
  knowledge,
  onClearKnowledge,
  onSend,
  onOpenQuestion,
}) {
  const stage = analysisStage(session.status);
  const structuralDisabled = busy || session.processing;
  const [renaming, setRenaming] = useState(false),
    [titleDraft, setTitleDraft] = useState(session.title);
  return (
    <div className="study-layout">
      <div className="study-main">
        <div className="page-title">
          <div>
            <span className="eyebrow">STUDY SESSION</span>
            {renaming ? (
              <div className="actions title-editor">
                <input
                  aria-label="学习名称"
                  maxLength={100}
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                />
                <button
                  className="secondary compact"
                  disabled={structuralDisabled || !titleDraft.trim()}
                  onClick={() =>
                    run(
                      () =>
                        api.patchSession(session.id, {
                          title: titleDraft.trim(),
                        }),
                      (s) => {
                        update(s);
                        setRenaming(false);
                      },
                    )
                  }
                >
                  保存名称
                </button>
                <button
                  className="text-link"
                  onClick={() => setRenaming(false)}
                >
                  取消
                </button>
              </div>
            ) : (
              <h1>
                {session.title || "新的学习"}{" "}
                <button
                  className="icon-button"
                  aria-label="修改学习名称"
                  disabled={structuralDisabled}
                  onClick={() => {
                    setTitleDraft(session.title);
                    setRenaming(true);
                  }}
                >
                  <Pencil size={16} />
                </button>
              </h1>
            )}
            <p>{session.questions?.length || 0} 道题目 · 从题目连接到知识</p>
          </div>
          <UploadButton onFiles={onFiles} busy={structuralDisabled} />
        </div>
        {session.attachments?.length > 0 && (
          <div className="attachments">
            {session.attachments.map((a) => (
              <div className="attachment-chip" key={a.id}>
                {a.url ? (
                  <a href={a.url} target="_blank" rel="noreferrer">
                    <FileImage size={13} />
                    {a.name}
                  </a>
                ) : (
                  <span>{a.name} · 原图已清理</span>
                )}
                {a.url && (
                  <button
                    aria-label={`清理原图 ${a.name}`}
                    disabled={structuralDisabled}
                    onClick={() =>
                      window.confirm("清理这张原图？已识别的题目仍会保留。") &&
                      run(() => api.deleteAttachment(session.id, a.id), update)
                    }
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        {(session.processing || stage.active) && (
          <Loading>
            {session.processing ? "后台处理中" : stage.title}
            {session.processing &&
              ` · 已完成 ${session.questions.filter((q) => q.analysis?.status === "confirmed").length}/${session.questions.length} 题`}
          </Loading>
        )}
        {session.error && <p className="notice error">{session.error}</p>}
        {session.questions?.map((q) => (
          <QuestionCard
            key={q.id}
            question={q}
            session={session}
            selected={q.id === selectedId}
            onSelect={() => {
              onClearKnowledge();
              setSelectedId(q.id);
              document.querySelector(".chat-composer textarea")?.focus();
            }}
            busy={busy}
            run={run}
            update={update}
            wiki={wiki}
            onKnowledge={onKnowledge}
            onExpand={() =>
              onSend(
                "请在不直接泄露其他题答案的前提下，详细展开这道题的解析。",
                q.id,
              )
            }
            onOpenQuestion={onOpenQuestion}
          />
        ))}
        {!session.questions?.length && (
          <UploadButton onFiles={onFiles} busy={structuralDisabled} large />
        )}
        {session.attachments?.some((a) => !a.extracted && !a.deleted) &&
          !structuralDisabled && (
            <button
              className="secondary"
              onClick={() => run(() => api.process(session.id), update)}
            >
              <RefreshCw size={15} />
              重新识别并解答
            </button>
          )}
      </div>
      <Conversation
        session={session}
        selected={session.questions?.find((q) => q.id === selectedId)}
        knowledge={knowledge}
        busy={busy}
        onSend={onSend}
        onKnowledge={onKnowledge}
        linkedKnowledgeIds={new Set((wiki?.nodes || []).map((n) => n.id))}
        onClear={() => {
          setSelectedId(null);
          onClearKnowledge();
        }}
      />
    </div>
  );
}
