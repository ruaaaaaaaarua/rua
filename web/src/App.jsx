import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  CircleHelp,
  Home,
  LoaderCircle,
  Menu,
  Plus,
  RotateCcw,
  Settings as SettingsIcon,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { api } from "./api.js";
import Study, { Dashboard } from "./Study.jsx";
import Knowledge from "./Knowledge.jsx";
import Reviews from "./Reviews.jsx";
import Settings from "./Settings.jsx";
import { dateText } from "./ui.jsx";
import "./styles.css";

const nav = [
  { id: "study", name: "学习台", Icon: Home },
  { id: "wiki", name: "知识库", Icon: BookOpen },
  { id: "reviews", name: "复习", Icon: RotateCcw },
];
export function mergePolledSession(current, latest) {
  if (!current || current.id !== latest.id) return current;
  const savedIds = new Set((latest.messages || []).map((message) => message.id));
  const transient = (current.messages || []).filter(
    (message) => {
      if (!message.transient || savedIds.has(message.id)) return false;
      if (message.role !== "user") return true;
      const known = new Set(message.known_message_ids || []);
      const persisted = (latest.messages || []).some(
        (saved) =>
          !known.has(saved.id) &&
          saved.role === "user" &&
          saved.content === message.content &&
          (saved.question_id || null) === (message.question_id || null) &&
          (saved.question_revision || null) ===
            (message.question_revision || null),
      );
      return !persisted;
    },
  );
  return { ...latest, messages: [...(latest.messages || []), ...transient] };
}

export function questionContext(session, selectedId, explicitId) {
  const questionId = explicitId || selectedId;
  if (!questionId) return {};
  const question = session?.questions?.find((item) => item.id === questionId);
  return { question_id: questionId, question_revision: question?.revision || 1 };
}

export default function App() {
  const [page, setPage] = useState("study"),
    [sessions, setSessions] = useState([]),
    [session, setSession] = useState(null);
  const [wiki, setWiki] = useState(null),
    [reviews, setReviews] = useState({ items: [], due_count: 0, total: 0 }),
    [settings, setSettings] = useState(null);
  const [chapter, setChapter] = useState("all"),
    [node, setNode] = useState(null),
    [chatKnowledge, setChatKnowledge] = useState(null);
  const [selected, setSelected] = useState(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState(""),
    [mobile, setMobile] = useState(false);
  const lock = useRef(false);
  const sessionEpoch = useRef(0);
  const updateSession = (value) => {
    sessionEpoch.current += 1;
    setSession(value);
  };
  const refresh = async () => {
    const [ss, ww, rr] = await Promise.all([
      api.sessions(),
      api.wiki(),
      api.reviews(),
    ]);
    setSessions(ss.filter((s) => !s.demo));
    setWiki(ww);
    setReviews(rr);
  };
  useEffect(() => {
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!session?.processing) return;
    const id = session.id;
    let active = true;
    let timer;
    const poll = async () => {
      const epoch = sessionEpoch.current;
      try {
        const latest = await api.session(id);
        if (!active) return;
        if (epoch !== sessionEpoch.current) return;
        setSession((current) => mergePolledSession(current, latest));
        if (!latest.processing) refresh().catch(() => {});
      } catch (e) {
        if (active) setError(e.message || "后台处理状态更新失败");
      } finally {
        if (active) timer = setTimeout(poll, 1000);
      }
    };
    timer = setTimeout(poll, 1000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [session?.id, session?.processing]);
  const run = async (fn, after) => {
    if (lock.current) return null;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      after?.(result);
      await refresh();
      return result;
    } catch (e) {
      setError(e.message || "操作未完成，请稍后重试");
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const openSession = (id, qid = null) =>
    run(async () => {
      let s = await api.session(id);
      updateSession(s);
      setPage("study");
      setSelected(qid);
      setChatKnowledge(null);
      setMobile(false);
      if (s.processing || ["recognizing", "extracted", "analyzing"].includes(s.status)) {
        s = await api.process(id);
        updateSession((current) => (current?.id === id ? s : current));
      }
      return s;
    });
  const goPage = (id) => {
    setPage(id);
    setMobile(false);
    if (id === "study") {
      updateSession(null);
      setSelected(null);
      setChatKnowledge(null);
    }
  };
  const openKnowledge = (id) => {
    setNode(id);
    setPage("wiki");
    setMobile(false);
  };
  const upload = (files) =>
    run(async () => {
      if (
        files.some(
          (f) =>
            ![
              "image/png",
              "image/jpeg",
              "image/webp",
              "image/heic",
              "image/heif",
            ].includes(f.type) &&
            !/\.(heic|heif|jpe?g|png|webp)$/i.test(f.name),
        )
      )
        throw new Error(
          "格式不支持：" +
            files.find(
              (f) =>
                ![
                  "image/png",
                  "image/jpeg",
                  "image/webp",
                  "image/heic",
                  "image/heif",
                ].includes(f.type) &&
                !/\.(heic|heif|jpe?g|png|webp)$/i.test(f.name),
            )?.name +
            "。请选择 HEIC、JPEG、PNG 或 WebP。",
        );
      if (files.length > 12)
        throw new Error(`本次选择了 ${files.length} 张图片，一次最多 12 张。`);
      const oversized = files.find((f) => f.size > 50 * 1024 * 1024);
      if (oversized)
        throw new Error(
          `${oversized.name} 为 ${(oversized.size / 1024 / 1024).toFixed(1)} MB，上传上限为 50 MB，请先缩小图片。`,
        );
      let s = page === "study" && session ? session : await api.createSession();
      updateSession(s);
      setPage("study");
      setMobile(false);
      s = await api.upload(s.id, files);
      updateSession(s);
      s = await api.process(s.id);
      updateSession((current) => (current?.id === s.id ? s : current));
      return s;
    });
  const send = async (text, explicitQuestionId = null) => {
    const result = await run(async () => {
      const s =
        session ||
        (await api.createSession({ title: chatKnowledge?.name || "学习对话" }));
      const id = s.id;
      if (!session) updateSession(s);
      const tags = questionContext(s, selected, explicitQuestionId);
      const knownMessageIds = (s.messages || []).map((message) => message.id);
      const transientId = `stream-${Date.now()}`;
      updateSession((current) => {
        if (current?.id !== id) return current;
        return {
          ...current,
          messages: [
            ...(current.messages || []),
            {
              id: `${transientId}-user`,
              role: "user",
              content: text,
              transient: true,
              known_message_ids: knownMessageIds,
              ...tags,
            },
            { id: transientId, role: "assistant", content: "", transient: true, ...tags },
          ],
        };
      });
      let streamed = "";
      try {
        const updated = await api.messageStream(id, {
        text,
        ...(tags.question_id ? { question_id: tags.question_id } : {}),
        ...(chatKnowledge ? { knowledge_id: chatKnowledge.id } : {}),
        }, (delta) => {
          streamed += delta;
          updateSession((current) =>
            current?.id === id
              ? {
                  ...current,
                  messages: current.messages.map((message) =>
                    message.id === transientId
                      ? { ...message, content: streamed }
                      : message,
                  ),
                }
              : current,
          );
        });
        updateSession((current) => (current?.id === id ? updated : current));
        return updated;
      } catch (e) {
        updateSession((current) =>
          current?.id === id
            ? {
                ...current,
                messages: current.messages.map((message) =>
                  message.id === transientId
                    ? {
                        ...message,
                        content: `${streamed}${streamed ? "\n\n" : ""}回复中断：${e.message}`,
                        interrupted: true,
                      }
                    : message,
                ),
              }
            : current,
        );
        throw e;
      }
    });
    return !!result;
  };
  const ask = (node) =>
    run(async () => {
      const s = await api.createSession({ title: node.name + " · 学习对话" });
      updateSession(s);
      setPage("study");
      setSelected(null);
      setChatKnowledge(node);
      return s;
    });
  const remove = (id) => {
    if (session?.id === id && session.processing) return;
    if (
      !window.confirm(
        "删除这次学习及其个人题目、复习安排？核心知识库不受影响。",
      )
    )
      return;
    run(
      () => api.deleteSession(id, true),
      () => {
        if (session?.id === id) {
          updateSession(null);
          setSelected(null);
        }
      },
    );
  };
  return (
    <div className="app-shell">
      {mobile && (
        <button
          className="sidebar-shade"
          aria-label="收起导航"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            goPage("study");
          }}
        >
          <span className="brand-icon">
            <Zap size={23} strokeWidth={1.5} />
          </span>
          <div>
            <strong>知序</strong>
            <small>POWER SYSTEMS</small>
          </div>
          <button
            className="mobile-close icon-button"
            aria-label="关闭导航"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setMobile(false);
            }}
          >
            <X size={18} />
          </button>
        </a>
        <div className="subject-card">
          <span className="status-dot" />
          <div>
            <strong>电力系统分析</strong>
            <small>我的专业课学习空间</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <button
          className="new-session"
          disabled={busy}
          onClick={() => {
            updateSession(null);
            setSelected(null);
            setPage("study");
            setChatKnowledge(null);
            setMobile(false);
          }}
        >
          <Plus size={17} />
          开始新的学习<span>↗</span>
        </button>
        <div className="nav-label">学习空间</div>
        <nav>
          {nav.map(({ id, name, Icon }) => (
            <button
              disabled={busy}
              className={page === id ? "active" : ""}
              key={id}
              onClick={() => goPage(id)}
            >
              <Icon size={18} strokeWidth={1.6} />
              {name}
              {id === "reviews" && reviews.due_count > 0 && (
                <span className="nav-count">{reviews.due_count}</span>
              )}
              {page === id && <span className="active-mark" />}
            </button>
          ))}
        </nav>
        <div className="nav-label history-label">
          最近学习<span>{sessions.length}</span>
        </div>
        <div className="session-list">
          {sessions.slice(0, 15).map((s) => (
            <div
              className={`session-entry ${session?.id === s.id && page === "study" ? "active" : ""}`}
              key={s.id}
            >
              <button disabled={busy} onClick={() => openSession(s.id)}>
                <span>{s.title}</span>
                <small>{dateText(s.updated_at)}</small>
              </button>
              <button
                disabled={busy || (session?.id === s.id && session.processing)}
                className="session-delete"
                aria-label={`删除学习 ${s.title}`}
                onClick={() => remove(s.id)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {!sessions.length && (
            <p className="history-empty">第一道题，会从这里开始。</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span>一点一滴，连成体系。</span>
            <small>题目 · 知识 · 回顾</small>
          </div>
          <button
            disabled={busy}
            onClick={() => run(() => api.settings(), setSettings)}
          >
            <SettingsIcon size={17} />
            模型设置
            <ArrowUpRight size={14} />
          </button>
          <div className="local-status">
            <span />
            记录保存在本机
          </div>
        </div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="打开导航"
            onClick={() => setMobile(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <span>我的学习空间</span>
            <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === page)?.name}</strong>
          </div>
          <div className="topbar-right">
            {busy ? (
              <span className="working">
                <LoaderCircle size={14} className="spin" />
                正在处理
              </span>
            ) : (
              <span className="subject-label">电力系统分析</span>
            )}
            <span className="avatar">学</span>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <CircleHelp size={17} />
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="关闭提示"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="main-content">
          {loading ? (
            <div className="loading">
              <LoaderCircle size={20} className="spin" />
              正在打开学习空间…
            </div>
          ) : page === "wiki" ? (
            <Knowledge
              wiki={wiki}
              chapter={chapter}
              setChapter={setChapter}
              selected={node}
              onSelect={openKnowledge}
              onQuestion={openSession}
              onAsk={ask}
              run={run}
            />
          ) : page === "reviews" ? (
            <Reviews
              data={reviews}
              run={run}
              busy={busy}
              refresh={() => refresh().catch((e) => setError(e.message))}
            />
          ) : session ? (
            <Study
              key={session.id}
              session={session}
              selectedId={selected}
              setSelectedId={setSelected}
              wiki={wiki}
              busy={busy}
              run={run}
              update={updateSession}
              onFiles={upload}
              onKnowledge={openKnowledge}
              knowledge={chatKnowledge}
              onClearKnowledge={() => setChatKnowledge(null)}
              onSend={send}
            />
          ) : (
            <Dashboard
              sessions={sessions}
              wiki={wiki}
              reviews={reviews}
              busy={busy}
              onFiles={upload}
              onSession={openSession}
              onChapter={(id) => {
                setChapter(id);
                setNode(null);
                setPage("wiki");
              }}
              onReviews={() => goPage("reviews")}
            />
          )}
        </div>
      </main>
      {settings && (
        <Settings
          initial={settings}
          busy={busy}
          run={run}
          onClose={() => setSettings(null)}
        />
      )}
    </div>
  );
}
