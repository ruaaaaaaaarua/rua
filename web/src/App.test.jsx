import { describe, expect, it } from "vitest";
import { mergePolledSession, questionContext } from "./App.jsx";

describe("progressive session coordination", () => {
  it("preserves in-flight transient messages when merging a poll", () => {
    const current = {
      id: "s1",
      processing: true,
      messages: [
        { id: "saved", role: "assistant", content: "old" },
        { id: "stream-1", role: "assistant", content: "partial", transient: true },
      ],
    };
    const latest = {
      id: "s1",
      processing: true,
      questions: [{ id: "q1" }],
      messages: [{ id: "saved", role: "assistant", content: "old" }],
    };
    expect(mergePolledSession(current, latest).messages).toEqual(current.messages);
  });

  it("reconciles only a newly persisted matching transient user message", () => {
    const historic = {
      id: "old-user",
      role: "user",
      content: "same prompt",
      question_id: "q1",
      question_revision: 1,
    };
    const transient = {
      id: "stream-user",
      role: "user",
      content: "same prompt",
      question_id: "q1",
      question_revision: 1,
      transient: true,
      known_message_ids: ["old-user"],
    };
    const current = { id: "s1", messages: [historic, transient] };

    expect(
      mergePolledSession(current, { id: "s1", messages: [historic] }).messages,
    ).toContainEqual(transient);

    const persisted = { ...historic, id: "new-user" };
    expect(
      mergePolledSession(current, {
        id: "s1",
        messages: [historic, persisted],
      }).messages,
    ).toEqual([historic, persisted]);
  });

  it("builds expanded explanation context from the explicitly clicked question", () => {
    const session = {
      questions: [
        { id: "q1", revision: 2 },
        { id: "q2", revision: 4 },
      ],
    };
    expect(questionContext(session, "q1", "q2")).toEqual({
      question_id: "q2",
      question_revision: 4,
    });
  });
});
