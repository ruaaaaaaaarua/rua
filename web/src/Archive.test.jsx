import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import Archive from "./Archive.jsx";
import {
  archiveSvg,
  changeArchiveProfile,
  estimatedTextWidth,
  normalizeArchive,
  rejectedArchiveProfile,
  recoverRejectedArchive,
  wrapText,
} from "./archive.js";

const data = {
  profile: {
    nickname: '<Grid & "A">',
    signature: "稳稳地学 </text><script>x</script>",
    theme: "blueprint",
    selected_medals: ["earned", "locked"],
    show_stats: false,
  },
  stats: {
    questions: 8,
    linked_nodes: 3,
    review_days: 2,
    raw_questions: ["SECRET"],
  },
  medals: [
    {
      id: "earned",
      title: "第一次连接",
      description: "证据",
      earned: true,
      earned_at: "2026-09-17",
      evidence: [],
    },
    {
      id: "locked",
      title: "尚未获得",
      description: "未获得",
      earned: false,
      evidence: [],
    },
  ],
};

describe("archive share output", () => {
  it("escapes user text, excludes locked medals and omits stats by default", () => {
    const svg = archiveSvg(data);
    expect(svg).toContain("&lt;Grid &amp; &quot;A&quot;&gt;");
    expect(svg).not.toContain("<script>");
    expect(svg).toContain("&lt;/text&gt;&lt;script&gt;x&lt;/script&gt;");
    expect(svg).toContain("第一次连接");
    expect(svg).not.toContain("尚未获得");
    expect(svg).not.toContain("已核对题目");
    expect(svg).not.toContain("SECRET");
    expect(svg).not.toMatch(/<script|<foreignObject/i);
  });

  it("includes only approved aggregate stats when explicitly opted in", () => {
    const svg = archiveSvg({
      ...data,
      profile: { ...data.profile, show_stats: true },
    });
    expect(svg).toContain("已核对题目 8");
    expect(svg).toContain("已连接节点 3");
    expect(svg).toContain("复习日 2");
    expect(svg).not.toContain("SECRET");
  });

  it("falls back to paper for an invalid theme", () => {
    expect(
      normalizeArchive({ ...data, profile: { ...data.profile, theme: "neon" } })
        .profile.theme,
    ).toBe("paper");
  });

  it("preserves explicit blank profile text without inserting stock share copy", () => {
    const normalized = normalizeArchive({
      ...data,
      profile: { ...data.profile, nickname: "", signature: "" },
    });
    expect(normalized.profile.nickname).toBe("");
    const svg = archiveSvg({ ...data, profile: normalized.profile });
    expect(svg).not.toContain("学习者");
    expect(svg).not.toContain("把每次思考");
  });

  it("wraps long mixed-width text within the card and truncates with an ellipsis", () => {
    const svg = archiveSvg({
      ...data,
      profile: {
        ...data.profile,
        nickname: "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234",
        signature:
          "这是一段很长的中文签名 mixed-with-a-very-long-latin-signature-that-must-not-overflow-the-card-boundary",
      },
    });
    expect(svg).toContain("<tspan");
    expect(svg).toContain("…");
    expect(svg).not.toContain("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234");
    const signature =
      "把每次思考留在自己的档案里。这是一段长中文与 mixed Latin text 相结合的测试签名，用来检查分享卡排版。";
    expect(
      wrapText(signature, 29, 2).every(
        (line) => estimatedTextWidth(line, 17) <= 520,
      ),
    ).toBe(true);
  });

  it("renders scoped themes and no raw question data", () => {
    const html = renderToStaticMarkup(
      <Archive data={data} busy={false} run={() => {}} refresh={() => {}} />,
    );
    expect(html).toContain('class="archive-root"');
    expect(html).toContain('data-theme="blueprint"');
    expect(html).not.toContain("SECRET");
  });

  it("keeps archive theme styles scoped away from body and root", () => {
    const css = readFileSync(new URL("./archive.css", import.meta.url), "utf8");
    expect(css).not.toMatch(/(^|})\s*(body|:root|\.app-shell)\s*[{,]/m);
    expect(css).toContain('.archive-root[data-theme="blueprint"]');
  });

  it("clears stale save feedback whenever the archive draft changes", () => {
    expect(
      changeArchiveProfile(
        data.profile,
        { theme: "paper" },
        "已保存到本机档案",
      ),
    ).toEqual({ profile: { ...data.profile, theme: "paper" }, feedback: "" });
  });

  it("removes rejected medal selections while eligibility cannot be refreshed", () => {
    expect(rejectedArchiveProfile(data.profile)).toEqual({
      ...data.profile,
      selected_medals: [],
    });
  });

  it("keeps a safe profile and surfaces an error when save and eligibility refresh both fail", async () => {
    const recovered = await recoverRejectedArchive(data.profile, async () => {
      throw new Error("offline");
    });
    expect(recovered.profile.selected_medals).toEqual([]);
    expect(recovered.data).toBeNull();
    expect(recovered.error).toContain("无法刷新");
  });
});
