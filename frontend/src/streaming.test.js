import { describe, expect, it } from "vitest";

import { consumeEventStream } from "./streaming";


describe("consumeEventStream", () => {
  it("parses events split across transport chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: status\ndata: {"message":"Work'));
        controller.enqueue(encoder.encode('ing"}\n\nevent: delta\ndata: {"text":"# Hi"}\n\n'));
        controller.close();
      },
    });
    const events = [];

    await consumeEventStream(new Response(stream), (event, data) => events.push([event, data]));

    expect(events).toEqual([
      ["status", { message: "Working" }],
      ["delta", { text: "# Hi" }],
    ]);
  });
});
