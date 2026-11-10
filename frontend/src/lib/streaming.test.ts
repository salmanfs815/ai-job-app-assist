import { describe, expect, it } from "vitest";

import { consumeEventStream } from "@/lib/streaming";

function streamOf(...chunks: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
  );
}

describe("consumeEventStream", () => {
  it("parses events split across transport chunks", async () => {
    const events: [string, unknown][] = [];

    await consumeEventStream(
      streamOf('event: status\ndata: {"message":"Work', 'ing"}\n\nevent: delta\ndata: {"text":"# Hi"}\n\n'),
      (event, data) => events.push([event, data]),
    );

    expect(events).toEqual([
      ["status", { message: "Working" }],
      ["delta", { text: "# Hi" }],
    ]);
  });

  it("handles CRLF line endings, comments and a final event without a blank line", async () => {
    const events: [string, unknown][] = [];

    await consumeEventStream(
      streamOf(': keep-alive\r\n\r\ndata: {"a":1}\r\n\r\nevent: done\r\ndata: {"demo":true}'),
      (event, data) => events.push([event, data]),
    );

    expect(events).toEqual([
      ["message", { a: 1 }],
      ["done", { demo: true }],
    ]);
  });

  it("rejects responses without a body", async () => {
    await expect(consumeEventStream(new Response(null), () => undefined)).rejects.toThrow("Streaming is not supported");
  });
});
