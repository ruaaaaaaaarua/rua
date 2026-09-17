import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import Study, {
  Conversation,
  appendMissingOption,
  buildQuestionPatch,
} from "./Study.jsx";

const q = {
  id: "q1",
  number: 1,
  revision: 1,
  kind: "single",
  text: "测试题干",
  options: [
    { key: "A", text: "选项甲" },
    { key: "B", text: "选项乙" },
  ],
  user_answer: "A",
  analysis: {
    status: "confirmed",
    correct: false,
    answer: "B",
    explanation: "SECRET_EXPLANATION",
  },
};
const s = {
  id: "s",
  title: "电力系统分析1 · 260915",
  questions: [q],
  messages: [],
  attachments: [],
};
const noop = () => {};
const props = {
  session: s,
  run: noop,
  update: noop,
  setSelectedId: noop,
  onClearKnowledge: noop,
  onFiles: noop,
  onKnowledge: noop,
  onSend: noop,
};

describe("photo-first study", () => {
  it("requires explicit completeness confirmation and adds bounded missing options", () => {
    const incomplete = { ...q, incomplete: true };
    expect(buildQuestionPatch(incomplete, false)).not.toHaveProperty(
      "completeness_confirmed",
    );
    expect(buildQuestionPatch(incomplete, true)).toMatchObject({
      completeness_confirmed: true,
    });
    expect(
      appendMissingOption({ options: [{ key: "A", text: "one" }] }).options,
    ).toEqual([
      { key: "A", text: "one" },
      { key: "B", text: "" },
    ]);
    const full = {
      options: "ABCDEFGH".split("").map((key) => ({ key, text: key })),
    };
    expect(appendMissingOption(full)).toBe(full);
  });

  it("shows an incomplete OCR warning without implying confirmation", () => {
    const html = renderToStaticMarkup(
      <Study
        {...props}
        session={{ ...s, questions: [{ ...q, incomplete: true }] }}
      />,
    );
    expect(html).toContain("识别内容可能不完整");
    expect(html).not.toContain("completeness_confirmed");
  });
  it("shows correctness without requiring another answer or revealing the solution", () => {
    const html = renderToStaticMarkup(<Study {...props} />);
    expect(html).toContain("答错了");
    expect(html).toContain("给我一点提示");
    expect(html).not.toContain("提交作答");
    expect(html).not.toContain("SECRET_EXPLANATION");
    expect(html).not.toContain("参考答案：");
  });
  it("offers optional answering for an unanswered photo", () => {
    const html = renderToStaticMarkup(
      <Study
        {...props}
        session={{
          ...s,
          questions: [
            {
              ...q,
              user_answer: "",
              analysis: { ...q.analysis, correct: null },
            },
          ],
        }}
      />,
    );
    expect(html).toContain("提交作答");
    expect(html).not.toContain("答错了");
  });
  it("only renders messages for the chosen question and current revision", () => {
    const messages = [
      {
        id: "1",
        role: "user",
        content: "PRIVATE_Q2",
        question_id: "q2",
        question_revision: 1,
      },
      {
        id: "2",
        role: "user",
        content: "CURRENT_Q1",
        question_id: "q1",
        question_revision: 1,
      },
      {
        id: "3",
        role: "user",
        content: "OLD_Q1",
        question_id: "q1",
        question_revision: 0,
      },
    ];
    const html = renderToStaticMarkup(
      <Conversation session={{ ...s, messages }} selected={q} />,
    );
    expect(html).toContain("CURRENT_Q1");
    expect(html).not.toContain("PRIVATE_Q2");
    expect(html).not.toContain("OLD_Q1");
  });
  it("keeps confirmed question controls usable while background work continues", () => {
    const html = renderToStaticMarkup(
      <Study {...props} session={{ ...s, processing: true }} busy={false} />,
    );
    expect(html).toContain("后台处理中");
    expect(html).toMatch(/<button[^>]*>我再试一次<\/button>/);
    expect(html).toMatch(
      /<button[^>]*>[^<]*<svg[^>]*>[\s\S]*?查看解析<\/button>/,
    );
    expect(html).toMatch(
      /<button[^>]*>[^<]*<svg[^>]*>[\s\S]*?给我一点提示<\/button>/,
    );
  });
  it("disables pending question actions and structural edits while processing", () => {
    const pending = { ...q, id: "q2", number: 2, analysis: null };
    const html = renderToStaticMarkup(
      <Study
        {...props}
        session={{ ...s, processing: true, questions: [pending] }}
        busy={false}
      />,
    );
    expect(html).toMatch(/aria-label="编辑识别内容"[^>]*disabled/);
    expect(html).toMatch(/>追问这道题<\/button>/);
    expect(html).toMatch(
      /disabled=""[^>]*>[^<]*<svg[^>]*>[\s\S]*?给我一点提示<\/button>/,
    );
  });
  it("hides ordinary source badges but retains pending warnings", () => {
    const html = renderToStaticMarkup(<Study {...props} />);
    expect(html).not.toContain("模型补充");
    const pending = renderToStaticMarkup(
      <Study
        {...props}
        session={{
          ...s,
          questions: [{ ...q, analysis: { ...q.analysis, status: "pending" } }],
        }}
      />,
    );
    expect(pending).toContain("答案待确认");
  });
  it("shows related personal history only after the answer is revealed", () => {
    const historic = {
      ...q,
      related_history: [
        {
          session_id: "old",
          question_id: "oq",
          title: "上次学习",
          state: "曾答错",
          source_url: "/sessions/old?question=oq",
        },
      ],
    };
    const html = renderToStaticMarkup(
      <Study {...props} session={{ ...s, questions: [historic] }} />,
    );
    expect(html).not.toContain("上次学习");
  });
});
