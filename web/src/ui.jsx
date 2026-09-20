import { useEffect, useRef } from "react";
import { ArrowUpRight, BookOpen, LoaderCircle, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
      >
        {String(children || "")}
      </ReactMarkdown>
    </div>
  );
}
export function Modal({ title, onClose, children, wide = false }) {
  const ref = useRef();
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.focus();
    const handle = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const controls = [
          ...ref.current.querySelectorAll(
            'button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]',
          ),
        ];
        const first = controls[0],
          last = controls.at(-1);
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === ref.current)
        ) {
          e.preventDefault();
          last?.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        ref={ref}
        tabIndex={-1}
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="关闭弹窗"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
export function Empty({ icon: Icon = BookOpen, title, children }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon size={26} strokeWidth={1.4} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Sources({
  citations = [],
  knowledgeStatus,
  source,
  onKnowledge,
  linkedKnowledgeIds,
}) {
  return (
    <div className="sources">
      {citations.length > 0 ? (
        <details>
          <summary>查看参考记录（{citations.length}）</summary>
          <div className="actions">
            {citations.map((c) => {
              const linked = linkedKnowledgeIds?.has(c.id);
              const content = (
                <>
                  <BookOpen size={12} />
                  {c.name}
                  <span>v{c.version}</span>
                  {linked && <ArrowUpRight size={12} />}
                </>
              );
              return linked ? (
                <button
                  key={`${c.id}-${c.version}`}
                  className="source-chip"
                  onClick={() => onKnowledge?.(c.id)}
                >
                  {content}
                </button>
              ) : (
                <span
                  key={`${c.id}-${c.version}`}
                  className="source-chip plain-reference"
                >
                  {content}
                </span>
              );
            })}
          </div>
        </details>
      ) : knowledgeStatus === "empty" ? (
        <span className="notice">
          相关知识正文待填充，请对关键结论保持核对。
        </span>
      ) : null}
    </div>
  );
}
export function Loading({ children = "正在加载" }) {
  return (
    <div className="loading">
      <LoaderCircle size={16} className="spin" />
      {children}
    </div>
  );
}
export const dateText = (value) =>
  value
    ? new Date(value).toLocaleDateString("zh-CN", {
        month: "long",
        day: "numeric",
      })
    : "暂无日期";
