// Your Brain in every chat: one tab per AI app, the exact command or settings block to copy,
// and a plain way forward when there is no Brain yet.

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../test/render";
import { ConnectBrain } from "./ConnectBrain";

const connect = {
  ready: true,
  server: "contxt",
  vault: "C:\\Contxt\\brain\\vault",
  clients: [
    {
      client: "claude-code",
      label: "Claude Code",
      server: "contxt",
      command: 'claude mcp add --scope user contxt -- python -m brainkit --vault "C:\\Contxt\\brain\\vault" mcp',
      note: "Run this once in a terminal.",
    },
    {
      client: "codex",
      label: "Codex",
      server: "contxt",
      file: "~/.codex/config.toml",
      config: "[mcp_servers.contxt]\ncommand = 'python'\n",
      note: "Add this to that file, then start a new Codex session.",
    },
  ],
};

describe("connecting an AI app to the Brain", () => {
  it("shows the command for the first app and the settings block for another", async () => {
    mockApi({ "GET /api/brain/connect": connect });
    renderAt(<ConnectBrain />);
    expect(await screen.findByText(/claude mcp add --scope user contxt/)).toBeInTheDocument();
    expect(screen.getByText("Run once in a terminal")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Codex" }));
    expect(screen.getByText("Add to ~/.codex/config.toml")).toBeInTheDocument();
    expect(screen.getByText(/\[mcp_servers\.contxt\]/)).toBeInTheDocument();
    expect(screen.getByText(/start a new Codex session/)).toBeInTheDocument();
  });

  it("says how to make a Brain when there is none", async () => {
    mockApi({ "GET /api/brain/connect": { ready: false, server: "contxt", clients: [] } });
    renderAt(<ConnectBrain />);
    expect(await screen.findByText(/There is no Brain here yet/)).toBeInTheDocument();
    expect(screen.getByText("uv run contxt setup")).toBeInTheDocument();
  });
});
