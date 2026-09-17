import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  Lightbulb,
  LoaderCircle,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { api } from "./api.js";
import { buildClassification, visibleReviews } from "./domain.js";
import { AnswerChoices } from "./Study.jsx";
import { Empty, Markdown, dateText } from "./ui.jsx";

export { buildClassification };

function ReviewRunner({
  review,
  setReview,
  answer,
  setAnswer,
  run,
  busy,
  refresh,
}) {
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
        <p>历史原题复习 · 先试着自己回答。</p>
      </div>
      <section className="paper review-question">
        <div className="actions">
          <span className="pill neutral">历史原题</span>
          {review.help_kind === "assisted" && (
            <span className="pill warning">已使用提示 · 辅助作答</span>
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
              className="secondary"
              disabled={busy}
              onClick={() => run(() => api.hintReview(review.id), setReview)}
            >
              <Lightbulb size={15} />
              {review.hint ? "已有提示" : "给我一点提示"}
            </button>
            <button
              className="text-link"
              disabled={busy}
              onClick={() => run(() => api.revealReview(review.id), setReview)}
            >
              <Eye size={15} />
              查看讲解
            </button>
          </div>
        )}
        {review.hint && (
          <p className="review-hint">
            <Lightbulb size={14} />
            {review.hint}
          </p>
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
                : "已记录原题作答，不代表本组或陌生题已掌握。"}
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
                保留本次结果，选下一题
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export default function Reviews({
  data,
  run,
  busy,
  refresh,
  onOpenQuestion,
  onBudget,
}) {
  const [filter, setFilter] = useState("groups"),
    [review, setReview] = useState(null),
    [answer, setAnswer] = useState(""),
    [organize, setOrganize] = useState(null);
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
      <ReviewRunner
        {...{ review, setReview, answer, setAnswer, run, busy, refresh }}
      />
    );
  const items = visibleReviews(data?.items, filter === "all" ? "all" : filter);
  return (
    <div className="page review-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">REVISIT & REMEMBER</span>
          <h1>回到学过的地方。</h1>
          <p>代表题只是今日入口，每道原题仍保留自己的结果与日期。</p>
        </div>
        <span className="catalog-count">
          {data?.due_count || 0}
          <small>道题待复习</small>
        </span>
      </div>
      <section className="review-summary review-organize">
        <Sparkles size={21} />
        <div>
          <strong>AI 整理历史题目</strong>
          <p>
            明确触发后最多整理 12
            道未分类题。运行期间互动写入会暂停，当前页面会保留。
          </p>
          {organize && (
            <p className="organize-result">
              已分类 {organize.classified} · 失败 {organize.failed} · 剩余{" "}
              {organize.remaining}
            </p>
          )}
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() =>
            run(
              () => api.organizeReviews(),
              (value) => {
                setOrganize(value);
                refresh();
              },
            )
          }
        >
          {busy ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <Sparkles size={14} />
          )}
          整理未分类题
        </button>
      </section>
      <div className="review-budget">
        <label>
          今日推荐量
          <select
            value={data?.limit || 5}
            onChange={(e) => onBudget?.(Number(e.target.value))}
          >
            {[3, 5, 10].map((n) => (
              <option key={n} value={n}>
                {n} 道
              </option>
            ))}
          </select>
        </label>
        <span>已为你选出 {(data?.recommended || []).length} 道代表原题</span>
      </div>
      <div className="chapter-tabs">
        <button
          className={filter === "groups" ? "active" : ""}
          onClick={() => setFilter("groups")}
        >
          知识·方法组
        </button>
        <button
          className={filter === "due" ? "active" : ""}
          onClick={() => setFilter("due")}
        >
          待复习
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
          全部原题
        </button>
      </div>
      {filter === "groups" ? (
        <div className="review-groups">
          {(data?.groups || []).map((group) => (
            <article className="paper review-group" key={group.id}>
              <header>
                <div>
                  <span className="eyebrow">知识·方法组</span>
                  <h2>
                    {group.knowledge_name || "未分类"} ·{" "}
                    {group.method_label || "待分类"}
                  </h2>
                </div>
                <span className="pill neutral">
                  {group.difficulty_label || "难度待定"}
                </span>
              </header>
              <p className="muted">
                选为代表题：
                {group.reason ||
                  group.representative?.reason ||
                  "按到期时间与学习记录保守选择"}
                。难度与推荐原因是估计，不是能力认证。
              </p>
              {group.representative && (
                <ReviewItem
                  item={group.representative}
                  label="代表题"
                  start={start}
                  busy={busy}
                  onOpenQuestion={onOpenQuestion}
                />
              )}
            </article>
          ))}
          {!(data?.groups || []).length && (
            <Empty icon={RotateCcw} title="还没有可分组的题目">
              未分类题仍保留在“全部原题”，也可手动纠正分类。
            </Empty>
          )}
        </div>
      ) : items.length ? (
        <div className="review-list">
          {items.map((item, i) => (
            <ReviewItem
              key={`${item.session_id}-${item.question_id}`}
              item={item}
              index={i}
              start={start}
              busy={busy}
              onOpenQuestion={onOpenQuestion}
            />
          ))}
        </div>
      ) : (
        <Empty icon={RotateCcw} title="还没有这些复习安排">
          上传题目并完成解答后，系统会根据实际记录安排回顾。
        </Empty>
      )}
    </div>
  );
}

function ReviewItem({ item, index = 0, label, start, busy, onOpenQuestion }) {
  return (
    <article className="review-item">
      <span className="review-index">
        {label || String(index + 1).padStart(2, "0")}
      </span>
      <div className="review-item-copy">
        <div className="actions">
          <span className="pill neutral">{item.state}</span>
          <span className="pill neutral">
            {item.difficulty_label || item.difficulty || "难度待定"}
          </span>
          <span className="muted small">{dateText(item.due_at)}</span>
        </div>
        <h3>{item.text}</h3>
        <div className="mini-links">
          {(item.knowledge || []).map((k) => (
            <span key={k.id}>{k.name}</span>
          ))}
        </div>
        <p>{item.reason}</p>
        <button
          className="text-link"
          onClick={() => onOpenQuestion?.(item.session_id, item.question_id)}
        >
          查看原题与纠正分类
        </button>
      </div>
      <button className="secondary" disabled={busy} onClick={() => start(item)}>
        {item.due ? "开始复习" : "提前练习"}
        <ArrowRight size={14} />
      </button>
    </article>
  );
}
