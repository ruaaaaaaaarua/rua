import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  FileText,
  GitBranch,
  MessageSquare,
  Search,
} from "lucide-react";
import { api } from "./api.js";
import { Empty, Loading, Markdown } from "./ui.jsx";

export default function Knowledge({
  wiki,
  chapter,
  setChapter,
  selected,
  onSelect,
  onQuestion,
  onAsk,
  run,
}) {
  const [query, setQuery] = useState(""),
    [detail, setDetail] = useState(null),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let live = true;
    setDetail(null);
    if (!selected) return;
    setLoading(true);
    api
      .wikiNode(selected)
      .then((node) => {
        if (live) setDetail(node);
      })
      .catch((error) => run(() => Promise.reject(error)))
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [selected]);
  const nodes = (wiki?.nodes || []).filter(
    (n) =>
      (chapter === "all" || n.chapter_id === chapter) &&
      `${n.name} ${(n.aliases || []).join(" ")}`.includes(query),
  );
  if (selected)
    return (
      <div className="page wiki-detail">
        <button className="text-link" onClick={() => onSelect(null)}>
          <ArrowLeft size={15} />
          返回知识地图
        </button>
        {loading && <Loading />}
        {detail && (
          <>
            <div className="detail-heading">
              <span className="eyebrow">
                {wiki?.chapters?.find((c) => c.id === detail.chapter_id)
                  ?.name || "已连接知识点"}
              </span>
              <h1>{detail.name}</h1>
              <div className="actions">
                <span
                  className={`pill ${detail.status === "published" ? "success" : "neutral"}`}
                >
                  {detail.status === "published" ? "已发布" : "正文待填充"}
                </span>
                <span className="muted small">版本 {detail.version}</span>
                <span className="muted small">{detail.id}</span>
              </div>
            </div>
            <div className="wiki-detail-grid">
              <div>
                <section className="paper wiki-body">
                  {detail.has_content ? (
                    <>
                      <Markdown>{detail.content}</Markdown>
                      {detail.status !== "published" && (
                        <p className="notice">
                          草稿内容尚未发布，不作为讲解依据。
                        </p>
                      )}
                    </>
                  ) : (
                    <Empty icon={FileText} title="给这个知识点，留一页空白">
                      知识节点已就位。正文填充并审核发布后，学习助手会优先查阅这里的内容。
                    </Empty>
                  )}
                  <div className="wiki-body-footer">
                    <BookOpen size={15} />
                    <span>
                      {detail.has_content
                        ? "内容与版本由知识库维护者管理"
                        : "当前可作为题目与学习记录的容器"}
                    </span>
                    <button className="text-link" onClick={() => onAsk(detail)}>
                      聊聊这个知识点 <ArrowRight size={14} />
                    </button>
                  </div>
                </section>
                {detail.sources?.length > 0 && (
                  <section className="detail-section">
                    <h2>知识来源</h2>
                    <ul>
                      {detail.sources.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </section>
                )}
                <section className="detail-section">
                  <div className="section-top">
                    <h2>我的关联题目</h2>
                    <span className="muted small">
                      {(detail.questions || []).length} 道
                    </span>
                  </div>
                  {(detail.questions || []).length ? (
                    detail.questions.map((q) => (
                      <button
                        className="linked-question"
                        key={`${q.session_id}-${q.question_id}`}
                        onClick={() => onQuestion(q.session_id, q.question_id)}
                      >
                        <span className="card-icon">
                          <FileText size={16} />
                        </span>
                        <span>{q.text}</span>
                        <ArrowRight size={15} />
                      </button>
                    ))
                  ) : (
                    <p className="soft-empty">
                      上传一道相关题目后，在题目卡片中关联到这里。
                    </p>
                  )}
                </section>
              </div>
              <aside className="wiki-aside">
                <section className="paper">
                  <span className="eyebrow">我的学习记录</span>
                  <h3>{detail.learning?.state || "尚无学习记录"}</h3>
                  <p>
                    {detail.learning?.summary ||
                      "关联题目后，这里会显示可核对的学习记录。"}
                  </p>
                  <small>
                    记录关联题目的表现，不据此推断每个知识点都已掌握。
                  </small>
                </section>
                <section className="paper">
                  <span className="eyebrow">知识连接</span>
                  {detail.related?.length ? (
                    detail.related.map((r) => (
                      <button
                        className="relation"
                        key={`${r.type}-${r.id}`}
                        onClick={() => onSelect(r.id)}
                      >
                        <GitBranch size={14} />
                        <span>
                          <small>
                            {
                              {
                                prerequisite: "前置知识",
                                related: "相关知识",
                                contrast: "概念辨析",
                              }[r.type]
                            }
                          </small>
                          {r.name}
                        </span>
                        <ArrowRight size={14} />
                      </button>
                    ))
                  ) : (
                    <p className="muted">
                      关系待维护。填写前置、相关或易混关系后，会显示在这里。
                    </p>
                  )}
                </section>
              </aside>
            </div>
          </>
        )}
      </div>
    );
  return (
    <div className="page wiki-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">KNOWLEDGE ATLAS</span>
          <h1>把知识，连成一片。</h1>
          <p>电力系统分析的概念、方法与联系。</p>
        </div>
        <span className="catalog-count">
          {wiki?.nodes?.length || 0}
          <small>个知识节点</small>
        </span>
      </div>
      <div className="wiki-toolbar">
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="搜索知识库"
            placeholder="搜索概念、公式或关键词…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span className="muted small">
          {wiki?.published_count || 0} 篇正文已发布
        </span>
      </div>
      <div className="chapter-tabs">
        <button
          className={chapter === "all" ? "active" : ""}
          onClick={() => setChapter("all")}
        >
          全部章节
        </button>
        {(wiki?.chapters || []).map((c) => (
          <button
            key={c.id}
            className={chapter === c.id ? "active" : ""}
            onClick={() => setChapter(c.id)}
          >
            {c.name}
          </button>
        ))}
      </div>
      {wiki?.chapters
        .filter((c) => nodes.some((n) => n.chapter_id === c.id))
        .map((c, i) => (
          <section className="atlas-chapter" key={c.id}>
            <div className="section-top">
              <h2>
                <span className="chapter-index">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {c.name}
              </h2>
              <span className="muted small">
                {nodes.filter((n) => n.chapter_id === c.id).length} 个节点
              </span>
            </div>
            <div className="node-grid">
              {nodes
                .filter((n) => n.chapter_id === c.id)
                .map((n) => (
                  <button
                    className="node-card"
                    key={n.id}
                    onClick={() => onSelect(n.id)}
                  >
                    <div>
                      <BookOpen size={17} strokeWidth={1.4} />
                      <span
                        className={`pill ${n.status === "published" ? "success" : "neutral"}`}
                      >
                        {n.status === "published" ? "已发布" : "待填充"}
                      </span>
                    </div>
                    <h3>{n.name}</h3>
                    <p>{n.aliases?.slice(0, 3).join(" · ") || "概念与方法"}</p>
                    <footer>
                      <span>查看知识节点</span>
                      <ArrowRight size={15} />
                    </footer>
                  </button>
                ))}
            </div>
          </section>
        ))}
      {!nodes.length && (
        <Empty title={query ? "还没找到这个知识点" : "你的知识地图还是空的"}>
          {query
            ? "换个关键词，或清除章节筛选。"
            : "上传题目照片并完成分析后，与题目相连的知识点会出现在这里。"}
        </Empty>
      )}
      <div className="catalog-note">
        <span className="status-dot" />
        这里只展示与你的题目已建立连接的知识点。
      </div>
    </div>
  );
}
