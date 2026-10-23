// Help > Empty, error and recovery states (v4 slice 15). A reference: each state drawn with the
// app's own shared parts (Loading, Empty, Failure, Status), where you meet it, and how to make it
// happen for real. It holds none of the person's Brain.

import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { css } from "../css";
import { Btn, Empty, Failure, Loading, S, Status } from "../ui";

interface State {
  id: string;
  label: string;
  title: string;
  says: string;
  example: ReactNode;
  where: string;
  reproduce: string;
  go?: [string, string];
}

/** An error as the server sends it, so Failure draws the same title it would for real. */
const sample = (status: number, message: string) => new ApiError(status, { code: "reference", message });

const STATES: State[] = [
  {
    id: "empty-capture",
    label: "EMPTY · CAPTURE",
    title: "Nothing captured yet",
    says: "Paste something, drop in a file, or choose a folder for Scout. Nothing reaches your AI until you keep it.",
    example: <Empty title="Nothing captured yet">Paste something, drop in a file, or choose a folder for Scout.</Empty>,
    where: "Capture, before the first source.",
    reproduce: "Start a Brain from the empty starter (contxt setup --brain empty) and open Capture.",
    go: ["Open Capture", "/capture"],
  },
  {
    id: "empty-catchup",
    label: "EMPTY · CATCH UP",
    title: "Nothing waiting",
    says: "No proposals await review. New ones appear after you capture something or press Scan now.",
    example: <Empty title="Nothing waiting">No proposals await review.</Empty>,
    where: "Brain, Catch up, once every proposal is decided.",
    reproduce: "Keep or skip every waiting proposal in Catch up.",
    go: ["Open Catch up", "/brain/catch-up"],
  },
  {
    id: "loading",
    label: "LOADING · BRAIN",
    title: "Loading notes and sources",
    says: "Shown while the app waits for this computer's server. It never shows old numbers as if they were current.",
    example: (
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <Loading what="Loading notes and sources" />
        <span style={css("height:10px;border-radius:6px;background:var(--soft);width:80%")} />
        <span style={css("height:10px;border-radius:6px;background:var(--soft);width:56%")} />
      </div>
    ),
    where: "Any page, for the moment its data is on the way.",
    reproduce: "Open Brain right after starting the app, or slow the network in your browser's developer tools.",
    go: ["Open Brain", "/brain"],
  },
  {
    id: "stale-scout",
    label: "STALE · SCOUT",
    title: "Not inspected lately",
    says: "A Scout folder hasn't been scanned since its last inspection. Changes after that aren't in proposals or answers until you scan.",
    example: <Status kind="tentative">Last inspected some days ago</Status>,
    where: "Capture, Scout: the folder's last inspection date.",
    reproduce: "Add a folder to Scout, press Scan now, change a file in it, and don't scan again.",
    go: ["Scan now in Capture", "/capture"],
  },
  {
    id: "stale-note",
    label: "STALE · NOTE",
    title: "Not confirmed lately",
    says: "The note is still current and still sent, with a note that it may be out of date. It hasn't expired.",
    example: <Status kind="tentative">Not confirmed since its review date</Status>,
    where: "A note in Brain, and the rechecks in Catch up.",
    reproduce: "Shorten the review period in Settings, Approval, or wait past a note's review date.",
    go: ["Open Catch up", "/brain/catch-up"],
  },
  {
    id: "denied-file",
    label: "PERMISSION DENIED · FILE",
    title: "Can't read a file",
    says: "The operating system blocked access. Allow Contxt to read the folder, then retry. The other files were inspected.",
    example: (
      <div style={css("display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
        <Status kind="failed">Failed · see why</Status>
        <Failure error={sample(403, "The operating system denied access. Nothing was analysed.")} />
      </div>
    ),
    where: "Capture: the source's row and its detail.",
    reproduce: "Put a file your user account can't read in a Scout folder (deny Read in its file properties, or chmod 000), then press Scan now.",
    go: ["Open Capture", "/capture"],
  },
  {
    id: "denied-scope",
    label: "PERMISSION DENIED · SCOPE",
    title: "Restricted to another project",
    says: "Notes matched but belong to a project this request can't use. They weren't sent, and their contents aren't shown.",
    example: <Failure error={sample(403, "Some notes matched but belong to another project. They weren't sent.")} />,
    where: "The receipt under an answer, in Ask and in a project.",
    reproduce: "Connect an app limited to one project, then ask it about another project's notes.",
    go: ["Open Ask", "/ask"],
  },
  {
    id: "partial-apply",
    label: "PARTIAL FAILURE · APPLY",
    title: "Some changes applied, one didn't",
    says: "One note changed after you reviewed it, so that change wasn't applied. The others are saved. Nothing was applied twice.",
    example: <Failure error={sample(409, "A note changed after you reviewed it, so that change wasn't applied. The others are saved.")} />,
    where: "Catch up, after you keep several proposals at once.",
    reproduce: "Open Catch up, change the target note in another tab, then keep its proposal with others.",
    go: ["Open Catch up", "/brain/catch-up"],
  },
  {
    id: "partial-coverage",
    label: "PARTIAL COVERAGE · SOURCE",
    title: "Partly searchable",
    says: "Part of a source couldn't be read, so that part isn't searched or sent. The rest is.",
    example: <Status kind="partial">Partly searchable</Status>,
    where: "Capture: a source's status and its detail.",
    reproduce: "Capture a spreadsheet with a tab Contxt can't read, such as one built from merged cells.",
    go: ["Open Capture", "/capture"],
  },
  {
    id: "retry",
    label: "RETRY · ANALYSIS",
    title: "Distill didn't finish",
    says: "Your AI didn't respond in time. Your capture is saved. Retrying uses the same provider; nothing is sent anywhere else.",
    example: (
      <div style={css("display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
        <Status kind="retrying">Retrying…</Status>
        <Failure error={sample(0, "Your AI didn't respond in time. Your capture is saved.")} />
      </div>
    ),
    where: "Capture: a source while it's analysed.",
    reproduce: "Disconnect from the internet while a capture is analysed, then reconnect and retry.",
    go: ["Open Capture", "/capture"],
  },
  {
    id: "signin",
    label: "SIGN-IN EXPIRED · AI",
    title: "Your AI CLI needs you to sign in",
    says: "Distill and Ask are paused. Contxt won't switch to another provider. Sign in from a terminal, then check again.",
    example: <Status kind="failed">Signed out</Status>,
    where: "Agents, Knowledge agent: the sign-in health beside the provider. Also Settings, Your AI apps.",
    reproduce: "Sign out of the CLI the agent runs on, with that CLI's own sign-out, then open Agents and press Check again.",
    go: ["Check again in Agents", "/agents"],
  },
  {
    id: "recovery",
    label: "RECOVERY · AFTER RESTART",
    title: "Finished an interrupted apply",
    says: "The app closed partway through applying changes. On restart it checked each one and finished the rest without duplicating any.",
    example: <Status kind="confirmed">Finished after restart</Status>,
    where: "Activity, and the change's undo point.",
    reproduce: "Stop the app (contxt serve) while it applies several kept proposals, then start it again.",
    go: ["Open Activity", "/activity"],
  },
  {
    id: "words-only",
    label: "WORDS-ONLY · SEARCH",
    title: "Matching exact words only",
    says: "The meaning model isn't installed, so paraphrases can be missed. Quality for this mode is reported separately.",
    example: <Status kind="partial">Words-only search</Status>,
    where: "Settings, On this computer, and the knowledge agent's Search line.",
    reproduce: "Set up with contxt setup --offline, or before the meaning model has downloaded.",
    go: ["Open On this computer", "/settings?tab=computer"],
  },
];

export function StatesPage() {
  const navigate = useNavigate();
  return (
    <div className="gn-page" style={css("max-width:1120px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:30px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <span style={css(S.eyebrow)}>HELP · REFERENCE</span>
        <h1 style={css(S.h1)}>When things aren’t ready</h1>
        <span style={css("font:400 17px/1.5 Geist;color:var(--ink2);max-width:680px")}>
          Empty, loading, stale, blocked, partly failed, retrying and recovered. Each one says what happened and what to do next.
        </span>
      </div>
      <div role="note" style={css("padding:14px 16px;border-radius:14px;background:var(--soft);font:400 14px/1.5 Geist;color:var(--ink2)")}>
        A reference of states, not your Brain. Each example is drawn with the app's own parts and holds none of your notes, sources or numbers. Where you'll meet it, and how to make it happen for real, are under each one.
      </div>
      <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:14px")}>
        {STATES.map((s) => (
          <section
            key={s.id}
            aria-labelledby={`state-${s.id}`}
            style={css("padding:22px;border-radius:20px;background:var(--surface);box-shadow:var(--shadow);display:flex;flex-direction:column;gap:10px")}
          >
            <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>{s.label}</span>
            <span id={`state-${s.id}`} style={css("font:400 22px/1.25 Newsreader")}>
              {s.title}
            </span>
            <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{s.says}</span>
            <div aria-label={`How it looks: ${s.title}`} style={css("padding:12px;border-radius:14px;border:1px dashed var(--line2)")}>
              {s.example}
            </div>
            <div style={css("display:flex;flex-direction:column;gap:4px")}>
              <span style={css("font:500 12px Geist")}>Where you'll meet it</span>
              <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{s.where}</span>
              <span style={css("font:500 12px Geist;padding-top:4px")}>Make it happen for real</span>
              <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{s.reproduce}</span>
            </div>
            {s.go ? (
              <Btn kind="primarySm" style="align-self:flex-start;margin-top:auto;padding:8px 16px" onClick={() => navigate(s.go?.[1] ?? "/")}>
                {s.go[0]}
              </Btn>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
