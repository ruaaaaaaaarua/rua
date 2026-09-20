import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import Reviews, { buildClassification } from "./Reviews.jsx";

const noop = () => {};
const item = {
  session_id: "s1",
  question_id: "q1",
  text: "原题",
  number: 1,
  knowledge: [{ id: "k1", name: "标幺值" }],
  state: "近期答错",
  due: true,
  due_at: "2026-09-17",
  difficulty: "basic",
  reason: "基础且尚无独立证据",
};
const data = {
  items: [item],
  groups: [
    {
      id: "g1",
      knowledge_name: "标幺值",
      method_label: "计算求解",
      difficulty_label: "基础",
      representative: item,
      reason: item.reason,
      items: [item],
    },
  ],
  recommended: [item],
  due_count: 1,
  total: 1,
  limit: 5,
};

describe("personal reviews", () => {
  it("shows grouped representative, reason, selectable recommendation budget and originals", () => {
    const html = renderToStaticMarkup(
      <Reviews
        data={data}
        run={noop}
        busy={false}
        refresh={noop}
        onOpenQuestion={noop}
        onBudget={noop}
      />,
    );
    expect(html).toContain("知识·方法组");
    expect(html).toContain("代表题");
    expect(html).toContain("基础且尚无独立证据");
    expect(html).toContain('value="3"');
    expect(html).toContain('value="5"');
    expect(html).toContain('value="10"');
    expect(html).toContain("全部原题");
    expect(html).not.toContain("本组已通过");
  });

  it("renders only the bounded recommended representatives in the initial view", () => {
    const groups = Array.from({ length: 6 }, (_, index) => ({
      ...data.groups[0],
      id: `g${index}`,
      representative: {
        ...item,
        question_id: `q${index}`,
        text: `代表题${index}`,
      },
    }));
    const recommended = groups.slice(0, 3).map((group) => group.representative);
    const html = renderToStaticMarkup(
      <Reviews
        data={{ ...data, groups, recommended, limit: 3 }}
        run={noop}
        busy={false}
        refresh={noop}
        onOpenQuestion={noop}
        onBudget={noop}
      />,
    );
    expect(html).toContain("代表题0");
    expect(html).toContain("代表题2");
    expect(html).not.toContain("代表题3");
  });

  it("validates complete controlled correction payloads", () => {
    expect(() =>
      buildClassification(
        {
          knowledge_ids: ["k1"],
          primary_knowledge_id: "k1",
          method: "calculation",
          variant: "direct",
          difficulty: "basic",
          target: "base",
          methodCondition: "ratio",
          boundary: "same",
          reason: "人工确认",
        },
        {
          knowledgeIds: new Set(["k1"]),
          methods: new Set(["calculation"]),
          variants: new Set(["direct"]),
          difficulties: new Set(["basic"]),
        },
      ),
    ).not.toThrow();
    expect(() =>
      buildClassification(
        {
          knowledge_ids: ["bad"],
          primary_knowledge_id: "bad",
          method: "calculation",
          variant: "direct",
          difficulty: "basic",
          target: "",
          methodCondition: "",
          boundary: "",
          reason: "",
        },
        {
          knowledgeIds: new Set(["k1"]),
          methods: new Set(["calculation"]),
          variants: new Set(["direct"]),
          difficulties: new Set(["basic"]),
        },
      ),
    ).toThrow("分类");
  });
});
