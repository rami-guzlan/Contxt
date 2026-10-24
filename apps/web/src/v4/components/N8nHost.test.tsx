// Gnomon's own n8n: host it here once, start or stop it, open it to sign in to your apps.

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { N8nHost } from "./N8nHost";

const status = (over: Record<string, unknown> = {}) => ({ installed: false, installing: false, running: false, url: "http://127.0.0.1:5678", version: "1.123.84", line: "Not installed.", ...over });

describe("n8n on this computer", () => {
  it("installs n8n here on request", async () => {
    const calls = mockApi({ "GET /api/heartbeat/n8n/host": status(), "POST /api/heartbeat/n8n/host": status({ installing: true }) });
    renderAt(<N8nHost />);
    await userEvent.click(await screen.findByRole("button", { name: "Host n8n here" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "install" });
  });

  it("opens and stops a running n8n", async () => {
    const calls = mockApi({ "GET /api/heartbeat/n8n/host": status({ installed: true, running: true, line: "Running on this computer." }), "POST /api/heartbeat/n8n/host": status({ installed: true }) });
    renderAt(<N8nHost />);
    expect(await screen.findByRole("link", { name: "Open n8n" })).toHaveAttribute("href", "http://127.0.0.1:5678");
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "stop" });
  });
});
