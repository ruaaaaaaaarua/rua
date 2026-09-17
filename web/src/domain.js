export function questionProgress(questions = []) {
  return questions.reduce(
    (out, q) => {
      const answer = q.user_answer;
      if (Array.isArray(answer) ? answer.length : String(answer ?? "").trim())
        out.answered += 1;
      if (q.analysis?.status === "confirmed") out.confirmed += 1;
      if (q.analysis?.correct === true) out.correct += 1;
      if (q.analysis?.status === "pending") out.pending += 1;
      return out;
    },
    {
      total: questions.length,
      answered: 0,
      confirmed: 0,
      correct: 0,
      pending: 0,
    },
  );
}

const MIN_CONVERSATION_HEIGHT = 156;
const DEFAULT_CONVERSATION_HEIGHT = 240;
const CONVERSATION_REST_HEIGHT = 240;

export function clampConversationHeight(value, viewportHeight) {
  const height = Number(value);
  const viewport = Number(viewportHeight);
  const maximum = Math.max(
    MIN_CONVERSATION_HEIGHT,
    viewport - CONVERSATION_REST_HEIGHT,
  );
  return Math.round(
    Math.min(
      Math.max(
        Number.isFinite(height) ? height : DEFAULT_CONVERSATION_HEIGHT,
        MIN_CONVERSATION_HEIGHT,
      ),
      maximum,
    ),
  );
}

export function savedConversationHeight(storage, viewportHeight) {
  let saved;
  try {
    saved = storage?.getItem?.("grid-learning.conversation-height");
  } catch {
    saved = null;
  }
  return clampConversationHeight(
    saved ?? DEFAULT_CONVERSATION_HEIGHT,
    viewportHeight,
  );
}

export function bindConversationResize(target, setHeight) {
  const reclamp = () =>
    setHeight((current) =>
      clampConversationHeight(current, target.innerHeight),
    );
  target.addEventListener("resize", reclamp);
  return () => target.removeEventListener("resize", reclamp);
}

const ANALYSIS_STAGES = {
  recognizing: {
    active: true,
    title: "正在识别图片",
    detail: "正在提取题目、选项和你的作答。",
  },
  extracted: {
    active: true,
    title: "题目已识别，正在独立解题",
    detail: "可以先核对题干与选项；答案与解析将随后补齐。",
  },
  analyzing: {
    active: true,
    title: "正在解题与检索知识库",
    detail: "正在整理答案、解析与可追溯的知识引用。",
  },
};

export const analysisStage = (status) =>
  ANALYSIS_STAGES[status] || { active: false, title: "", detail: "" };
export const shouldResumeAnalysis = (status) => status === "extracted";
export const analysisRunKey = (session) =>
  `${session?.id || ""}:${(session?.questions || [])
    .filter((q) => !q.analysis)
    .map((q) => q.id)
    .join(",")}`;

export function parseSseFrames(buffer) {
  const events = [];
  let rest = buffer;
  while (rest.includes("\n\n")) {
    const end = rest.indexOf("\n\n");
    const frame = rest.slice(0, end);
    rest = rest.slice(end + 2);
    const type = frame
      .split("\n")
      .find((line) => line.startsWith("event:"))
      ?.slice(6)
      .trim();
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (data) events.push({ type, data: JSON.parse(data) });
  }
  return { events, rest };
}

const KNOWLEDGE_STATES = {
  unseen: { key: "neutral", label: "尚无学习记录" },
  viewed: { key: "neutral", label: "已查看解析" },
  answered: { key: "neutral", label: "已有作答记录" },
  reviewed: { key: "success", label: "已有复习记录" },
};

export const answerText = (value) =>
  Array.isArray(value) ? value.join(",") : String(value ?? "");
export function toggleAnswer(value, key, kind) {
  if (kind !== "multiple") return key;
  const current = answerText(value)
    .split(/[,，、\s]+/)
    .filter(Boolean);
  return (
    current.includes(key)
      ? current.filter((item) => item !== key)
      : [...current, key]
  ).join(",");
}
export function visibleReviews(items = [], filter = "due") {
  return items.filter(
    (item) => filter === "all" || (filter === "due" ? item.due : !item.due),
  );
}

export function buildClassification(draft, allowed) {
  const ids = [...new Set(draft.knowledge_ids || [])];
  const valid =
    ids.length &&
    ids.every((id) => allowed.knowledgeIds.has(id)) &&
    ids.includes(draft.primary_knowledge_id) &&
    allowed.methods.has(draft.method) &&
    allowed.variants.has(draft.variant) &&
    allowed.difficulties.has(draft.difficulty) &&
    draft.target?.trim() &&
    draft.methodCondition?.trim() &&
    draft.boundary?.trim() &&
    draft.reason?.trim();
  if (!valid)
    throw new Error("分类需使用可用知识点并完整填写目标、方法和边界条件");
  return {
    knowledge_ids: ids,
    primary_knowledge_id: draft.primary_knowledge_id,
    method: draft.method,
    variant: draft.variant,
    conditions: [
      `target:${draft.target.trim()}`,
      `method:${draft.methodCondition.trim()}`,
      `boundary:${draft.boundary.trim()}`,
    ],
    difficulty: draft.difficulty,
    confidence: 1,
    reason: draft.reason.trim(),
  };
}

export function knowledgeState(state) {
  return (
    KNOWLEDGE_STATES[state] || { key: "unknown", label: state || "尚无记录" }
  );
}

export function groupKnowledge(rows = []) {
  const subjects = new Map();
  rows.forEach((item) => {
    const subject = item.subject || "未分类";
    const chapter = item.chapter || "其他";
    if (!subjects.has(subject)) subjects.set(subject, new Map());
    const chapters = subjects.get(subject);
    if (!chapters.has(chapter)) chapters.set(chapter, []);
    chapters.get(chapter).push(item);
  });
  return [...subjects].map(([subject, chapters]) => ({
    subject,
    chapters: [...chapters].map(([chapter, items]) => ({ chapter, items })),
  }));
}
