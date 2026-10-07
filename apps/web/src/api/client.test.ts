import { describe, expect, it } from "vitest";

import { mockApi } from "../test/render";
import { ApiError, get, post, query } from "./client";

describe("api client", () => {
  it("sends the CSRF header on writes but not on reads", async () => {
    const calls = mockApi({ "GET /api/me": { name: "Owner" }, "POST /api/goals": { id: "goal_1" } });
    await get("/api/me");
    await post("/api/goals", { title: "Grow" });
    expect(calls[0]?.headers["X-Workspace-CSRF"]).toBeUndefined();
    expect(calls[1]?.headers["X-Workspace-CSRF"]).toBe("1");
    expect(calls[1]?.body).toEqual({ title: "Grow" });
  });

  it("turns refusals into ApiError with the server's code and message", async () => {
    mockApi({
      "POST /api/tasks/t/ready": {
        status: 422,
        body: { error: { code: "invalid", message: "Assign the task to a model or person first." } },
      },
    });
    const error = await post("/api/tasks/t/ready").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).message).toBe("Assign the task to a model or person first.");
  });

  it("explains request validation errors", async () => {
    mockApi({
      "POST /api/goals": { status: 422, body: { detail: [{ loc: ["body", "title"], msg: "Field required" }] } },
    });
    const error = (await post("/api/goals", {}).catch((caught: unknown) => caught)) as ApiError;
    expect(error.message).toBe("title: Field required");
  });

  it("accepts empty responses", async () => {
    mockApi({ "DELETE /api/credentials/c1": { status: 204 } });
    const { del } = await import("./client");
    await expect(del("/api/credentials/c1")).resolves.toBeUndefined();
  });

  it("builds query strings without empty values", () => {
    expect(query({ status: "ready", project_id: undefined, q: "" })).toBe("?status=ready");
    expect(query({})).toBe("");
  });
});
