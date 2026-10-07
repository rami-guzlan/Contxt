// Your Brain in every chat: pick the AI app, copy one command or one settings block. The same
// text as `uv run contxt connect`, with this computer's paths already filled in.

import { useState } from "react";

import { useBrainConnect } from "../api/hooks";
import { CopyBlock, Empty, ErrorNote, Loading, Tabs } from "./ui";

export function ConnectBrain() {
  const { data, error, isLoading } = useBrainConnect();
  const [picked, setPicked] = useState<string | null>(null);
  if (isLoading) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  const client = data?.ready ? (data.clients.find((c) => c.client === picked) ?? data.clients[0]) : undefined;
  if (!data || !client) {
    return (
      <Empty why="There is no Brain here yet, so there is nothing to connect.">
        <p className="muted small">
          Make one in the Contxt folder with <code>uv run contxt setup</code>, then restart the app.
        </p>
      </Empty>
    );
  }
  return (
    <div className="connect-brain" data-tour="connect-brain">
      <Tabs
        tabs={data.clients.map((c) => ({ id: c.client, label: c.label }))}
        active={client.client}
        onChange={setPicked}
      />
      {client.command ? (
        <CopyBlock label="Run once in a terminal" text={client.command} />
      ) : (
        <CopyBlock label={client.file ? `Add to ${client.file}` : "Add to the app's MCP settings"} text={client.config ?? ""} />
      )}
      <p className="muted small">{client.note}</p>
      <p className="muted small">
        The app then shows a server called <code>{data.server}</code>. It reads your Brain from <code>{data.vault}</code> on this computer: no
        account, no token, nothing sent anywhere but to the AI app you connect.
      </p>
    </div>
  );
}
