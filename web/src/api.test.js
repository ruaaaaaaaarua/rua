import { it, expect, vi, afterEach } from "vitest";
import { api } from "./api.js";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it("polls saved results without resending analysis and stops after completion", async () => {
  vi.useFakeTimers();
  let finish;
  const post = new Promise((resolve) => {
    finish = resolve;
  });
  const response = (body) => ({
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => body,
  });
  const fetch = vi.fn((url, options) =>
    options?.method === "POST"
      ? post
      : Promise.resolve(
          response({ status: "analyzing", questions: [{ id: "q1" }] }),
        ),
  );
  vi.stubGlobal("fetch", fetch);
  const update = vi.fn();
  const work = api.analyze("s", update);
  await vi.advanceTimersByTimeAsync(650);
  expect(update).toHaveBeenCalledWith({
    status: "analyzing",
    questions: [{ id: "q1" }],
  });
  finish(response({ status: "ready" }));
  expect(await work).toEqual({ status: "ready" });
  const count = fetch.mock.calls.length;
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).toHaveBeenCalledTimes(count);
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "POST"),
  ).toHaveLength(1);
});

it("starts progressive processing without waiting for the background job", async () => {
  const response = (body) => ({
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => body,
  });
  const fetch = vi.fn(async () => response({ id: "s1", processing: true }));
  vi.stubGlobal("fetch", fetch);

  await expect(api.process("s1")).resolves.toEqual({
    id: "s1",
    processing: true,
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/sessions/s1/process",
    expect.objectContaining({ method: "POST" }),
  );
});

it("streams message deltas and returns the authoritative done session", async () => {
  const encoder = new TextEncoder();
  const chunks = [
    'event: delta\ndata: {"type":"delta","text":"第"}\n\n',
    'event: delta\ndata: {"type":"delta","text":"二段"}\n\nevent: done\ndata: {"type":"done","session":{"id":"s1","messages":[]}}\n\n',
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      headers: { get: () => "text/event-stream" },
      body: new ReadableStream({
        start(controller) {
          chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
          controller.close();
        },
      }),
    })),
  );
  const delta = vi.fn();

  await expect(
    api.messageStream("s1", { text: "解释" }, delta),
  ).resolves.toEqual({ id: "s1", messages: [] });
  expect(delta).toHaveBeenNthCalledWith(1, "第");
  expect(delta).toHaveBeenNthCalledWith(2, "二段");
});

it("rejects a message stream that ends before done", async () => {
  const encoder = new TextEncoder();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      headers: { get: () => "text/event-stream" },
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode(
              'event: delta\ndata: {"type":"delta","text":"未完成"}\n\n',
            ),
          );
          controller.close();
        },
      }),
    })),
  );

  await expect(api.messageStream("s1", { text: "继续" })).rejects.toThrow(
    "连接提前结束",
  );
});

it("cancels and releases the SSE reader after an error event", async () => {
  const encoder = new TextEncoder();
  const reader = {
    read: vi.fn(async () => ({
      done: false,
      value: encoder.encode(
        'event: error\ndata: {"type":"error","message":"broken"}\n\n',
      ),
    })),
    cancel: vi.fn(async () => {}),
    releaseLock: vi.fn(),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      headers: { get: () => "text/event-stream" },
      body: { getReader: () => reader },
    })),
  );

  await expect(api.messageStream("s1", { text: "continue" })).rejects.toThrow(
    "broken",
  );
  expect(reader.cancel).toHaveBeenCalledOnce();
  expect(reader.releaseLock).toHaveBeenCalledOnce();
});

it("uses bounded review, classification, organize and archive contracts", async () => {
  const response = (body = {}) => ({
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => body,
  });
  const fetch = vi.fn(async () => response({}));
  vi.stubGlobal("fetch", fetch);

  await api.reviews(10);
  await api.organizeReviews();
  await api.classifyQuestion("s 1", "q/1", { method: "concept" });
  await api.archive();
  await api.saveArchive({ theme: "paper" });

  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    "/api/reviews?limit=10",
    "/api/reviews/organize",
    "/api/sessions/s%201/questions/q%2F1/classification",
    "/api/archive",
    "/api/archive",
  ]);
  expect(fetch.mock.calls[1][1]).toMatchObject({ method: "POST" });
  expect(fetch.mock.calls[4][1]).toMatchObject({ method: "PUT" });
});
