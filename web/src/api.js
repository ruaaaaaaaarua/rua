import { parseSseFrames } from "./domain.js";

async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  const type = response.headers.get("content-type") || "";
  const body = type.includes("json")
    ? await response.json()
    : await response.text();
  if (!response.ok)
    throw new Error(
      body?.detail || body?.message || body || `请求失败 (${response.status})`,
    );
  return body;
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  sessions: () => request("/sessions"),
  session: (id) => request(`/sessions/${id}`),
  createSession: (body = {}) => request("/sessions", json("POST", body)),
  patchSession: (id, body) => request(`/sessions/${id}`, json("PATCH", body)),
  deleteSession: (id, deleteEvidence = false) =>
    request(`/sessions/${id}?delete_evidence=${deleteEvidence}`, {
      method: "DELETE",
    }),
  upload: (id, files) => {
    const body = new FormData();
    [...files].forEach((file) => body.append("files", file));
    return request(`/sessions/${id}/upload`, { method: "POST", body });
  },
  extract: (id) => request(`/sessions/${id}/extract`, json("POST", {})),
  process: (id) => request(`/sessions/${id}/process`, json("POST", {})),
  extractStream: async (id, onQuestion) => {
    const response = await fetch(`/api/sessions/${id}/extract-stream`, {
      method: "POST",
      headers: { Accept: "text/event-stream" },
    });
    if (!response.ok) {
      const type = response.headers.get("content-type") || "";
      const body = type.includes("json")
        ? await response.json()
        : await response.text();
      throw new Error(
        body?.detail ||
          body?.message ||
          body ||
          `请求失败 (${response.status})`,
      );
    }
    if (!response.body) throw new Error("浏览器不支持流式响应，请重试");
    const reader = response.body.getReader(),
      decoder = new TextDecoder();
    let buffer = "",
      completed = false;
    const receive = (chunk) => {
      buffer += decoder.decode(chunk, { stream: true });
      const parsed = parseSseFrames(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) {
        if (event.type === "question" && event.data.question)
          onQuestion?.(event.data.question);
        if (event.type === "error")
          throw new Error(event.data.message || "图片识别未完成，请重试");
        if (event.type === "done") completed = true;
      }
    };
    while (!completed) {
      const { done, value } = await reader.read();
      if (done) break;
      receive(value);
    }
    if (!completed) throw new Error("图片识别连接提前结束，请重试");
    return request(`/sessions/${id}`);
  },
  analyze: async (id, onProgress) => {
    let active = true,
      timer,
      polling;
    const poll = () => {
      polling = request(`/sessions/${id}`)
        .then((s) => {
          if (active) onProgress?.(s);
        })
        .catch(() => {})
        .finally(() => {
          if (active) timer = setTimeout(poll, 1000);
        });
    };
    if (onProgress) timer = setTimeout(poll, 600);
    try {
      return await request(`/sessions/${id}/analyze`, json("POST", {}));
    } finally {
      active = false;
      clearTimeout(timer);
      if (polling) await polling;
    }
  },
  hint: (id, qid) =>
    request(`/sessions/${id}/questions/${qid}/hint`, json("POST", {})),
  message: (id, body) =>
    request(`/sessions/${id}/messages`, json("POST", body)),
  messageStream: async (id, body, onDelta) => {
    const response = await fetch(`/api/sessions/${id}/messages-stream`, {
      ...json("POST", body),
      headers: { ...json("POST", body).headers, Accept: "text/event-stream" },
    });
    if (!response.ok) {
      const type = response.headers.get("content-type") || "";
      const value = type.includes("json")
        ? await response.json()
        : await response.text();
      throw new Error(
        value?.detail || value?.message || value || `请求失败 (${response.status})`,
      );
    }
    if (!response.body) throw new Error("浏览器不支持流式响应，请重试");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed = false;
    let session;
    const receive = (chunk, final = false) => {
      buffer += decoder.decode(chunk, { stream: !final });
      const parsed = parseSseFrames(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) {
        const type = event.type || event.data.type;
        if (type === "delta") onDelta?.(event.data.text || "");
        if (type === "error")
          throw new Error(event.data.message || "流式回复中断，请重试");
        if (type === "done") {
          completed = true;
          session = event.data.session;
        }
      }
    };
    try {
      while (!completed) {
        const { done, value } = await reader.read();
        if (done) {
          receive(new Uint8Array(), true);
          break;
        }
        receive(value);
      }
      if (!completed || !session)
        throw new Error("流式回复连接提前结束，请重试");
      return session;
    } finally {
      try {
        await reader.cancel();
      } catch {}
      reader.releaseLock?.();
    }
  },
  patchQuestion: (id, qid, body) =>
    request(`/sessions/${id}/questions/${qid}`, json("PATCH", body)),
  reveal: (id, qid) =>
    request(`/sessions/${id}/questions/${qid}/reveal`, json("POST", {})),
  retryQuestion: (id, qid, body) =>
    request(`/sessions/${id}/questions/${qid}/retry`, json("POST", body)),
  deleteAttachment: (id, aid) =>
    request(`/sessions/${id}/attachments/${aid}`, { method: "DELETE" }),
  recheck: (id, qid, text) =>
    request(`/sessions/${id}/questions/${qid}/recheck`, json("POST", { text })),
  reference: (id, text) =>
    request(`/sessions/${id}/reference`, json("POST", { text })),
  referenceUpload: (id, files) => {
    const body = new FormData();
    [...files].forEach((file) => body.append("files", file));
    return request(`/sessions/${id}/reference-upload`, {
      method: "POST",
      body,
    });
  },
  knowledge: () => request("/knowledge"),
  settings: () => request("/settings"),
  saveSettings: (body) => request("/settings", json("PUT", body)),
  testProfile: (profile_id) =>
    request("/settings/test", json("POST", { profile_id })),
  wiki: (q = "") => request(`/wiki?q=${encodeURIComponent(q)}`),
  wikiNode: (id) => request(`/wiki/${encodeURIComponent(id)}`),
  linkQuestion: (id, qid, knowledge_ids) =>
    request(
      `/sessions/${id}/questions/${qid}/links`,
      json("PUT", { knowledge_ids }),
    ),
  reviews: () => request("/reviews"),
  startReview: (body) => request("/reviews/start", json("POST", body)),
  revealReview: (id) => request(`/reviews/${id}/reveal`, json("POST", {})),
  answerReview: (id, answer) =>
    request(`/reviews/${id}/answer`, json("POST", { answer })),
};
