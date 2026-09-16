import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  Eye,
  RotateCcw,
} from "lucide-react";
import { api } from "./api.js";
import { visibleReviews } from "./domain.js";
import { AnswerChoices } from "./Study.jsx";
import { Empty, Markdown, dateText } from "./ui.jsx";

export default function Reviews({ data, run, busy, refresh }) {
  const [filter, setFilter] = useState("due"),
    [review, setReview] = useState(null),
    [answer, setAnswer] = useState("");
  const start = (item) =>
    run(
      () =>
        api.startReview({
          session_id: item.session_id,
          question_id: item.question_id,
        }),
      (value) => {
        setReview(value);
        setAnswer("");
      },
    );
  if (review)
    return (
      <div className="page review-page">
        <button
          className="text-link"
          onClick={() => {
            setReview(null);
            refresh();
          }}
        >
          <ArrowLeft size={15} />
          返回复习安排
        </button>
        <div className="detail-heading">
          <span className="eyebrow">A SECOND LOOK</span>
          <h1>再想一次。</h1>
          <p>历史原题复习 · 这一次，先试着自己回答。</p>
        </div>
        <section className="paper review-question">
          <div className="actions">
            <span className="pill neutral">历史原题</span>
            {review.help_kind === "assisted" && (
              <span className="pill warning">近期已查看讲解 · 辅助作答</span>
            )}
          </div>
          <Markdown>{review.question.text}</Markdown>
          <AnswerChoices
            question={review.question}
            value={answer}
            onChange={setAnswer}
            disabled={busy || review.status === "answered"}
          />
          {review.status === "ready" && (
            <div className="actions review-actions">
              <button
                className="primary"
                disabled={busy || !answer.trim()}
                onClick={() =>
                  run(
                    () => api.answerReview(review.id, answer),
                    (value) => {
                      setReview(value);
                      refresh();
                    },
                  )
                }
              >
                提交这次答案 <ArrowRight size={15} />
              </button>
              <button
                className="text-link"
                disabled={busy}
                onClick={() =>
                  run(() => api.revealReview(review.id), setReview)
                }
              >
                <Eye size={15} />
                查看讲解
              </button>
            </div>
          )}
          {review.answer && (
            <div className="review-result">
              {review.status === "answered" && (
                <h3>{review.correct ? "这次答对了。" : "这次还需要回顾。"}</h3>
              )}
              <strong>参考答案：{review.answer}</strong>
              <Markdown>{review.explanation}</Markdown>
              <p className="muted small">
                {review.help_kind === "assisted"
                  ? "已记录为得到帮助后的作答。"
                  : "已记录原题作答，不代表陌生题能力。"}
                {review.next_due_at &&
                  ` 下次回顾：${dateText(review.next_due_at)}。`}
              </p>
              {review.status === "answered" && (
                <button
                  className="secondary"
                  onClick={() => {
                    setReview(null);
                    refresh();
                  }}
                >
                  <Check size={15} />
                  完成本次复习
                </button>
              )}
            </div>
          )}
        </section>
      </div>
    );
  const items = visibleReviews(data?.items, filter);
  return (
    <div className="page review-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">REVISIT & REMEMBER</span>
          <h1>回到学过的地方。</h1>
          <p>让一次解答，变成可以再次想起的知识。</p>
        </div>
        <span className="catalog-count">
          {data?.due_count || 0}
          <small>道题待复习</small>
        </span>
      </div>
      <div className="review-summary">
        <CalendarDays size={21} strokeWidth={1.5} />
        <div>
          <strong>
            {data?.due_count ? "今天的回顾已准备好" : "按自己的节奏，再看一次"}
          </strong>
          <p>
            依据作答记录安排原题回顾。到期只意味着建议复习，不代表已经遗忘。
          </p>
        </div>
      </div>
      <div className="chapter-tabs">
        <button
          className={filter === "due" ? "active" : ""}
          onClick={() => setFilter("due")}
        >
          待复习 <span>{data?.due_count || 0}</span>
        </button>
        <button
          className={filter === "upcoming" ? "active" : ""}
          onClick={() => setFilter("upcoming")}
        >
          之后再看
        </button>
        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          全部安排
        </button>
      </div>
      {items.length ? (
        <div className="review-list">
          {items.map((q, i) => (
            <article
              className="review-item"
              key={`${q.session_id}-${q.question_id}`}
            >
              <span className="review-index">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="review-item-copy">
                <div className="actions">
                  <span className="pill neutral">{q.state}</span>
                  <span className="muted small">{dateText(q.due_at)}</span>
                </div>
                <h3>{q.text}</h3>
                <div className="mini-links">
                  {q.knowledge.map((k) => (
                    <span key={k.id}>{k.name}</span>
                  ))}
                </div>
                <p>{q.reason}</p>
              </div>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => start(q)}
              >
                {q.due ? "开始复习" : "提前练习"}
                <ArrowRight size={14} />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          icon={RotateCcw}
          title={filter === "due" ? "今天没有到期的复习" : "还没有这些复习安排"}
        >
          {data?.total
            ? "可以查看之后的安排，或继续上传新的题目。"
            : "上传题目并完成解答后，系统会根据实际记录安排回顾。"}
        </Empty>
      )}
    </div>
  );
}
