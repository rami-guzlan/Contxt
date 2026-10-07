// Adding a file to the Brain: into a project (or a new one), in at once with an Undo, or
// waiting for review when the Brain's policy says so. Used wherever files come in.

import { type FormEvent, useState } from "react";
import { Link } from "react-router";

import { useBrainCatalog, useBrainProjects, useBrainUndo, useCreateBrainProject, useFileInBrain } from "../../api/hooks";
import type { BrainFiled } from "../../api/types";
import { ErrorNote, Field } from "../../components/ui";
import { label } from "../../lib/format";

const NEW_PROJECT = "__new__";
const STATUSES = ["draft", "sent", "final"] as const;

/** Add a file to the Brain: into a project (or a new one), in at once with an Undo, or
 * waiting for review when the Brain's policy says so. */
export function AddFileDialog({ onClose, project: preset }: { onClose: () => void; project?: string }) {
  const { data: catalog } = useBrainCatalog();
  const { data: projects } = useBrainProjects();
  const createProject = useCreateBrainProject();
  const fileIt = useFileInBrain();
  const undo = useBrainUndo();
  const [file, setFile] = useState<File | null>(null);
  const [project, setProject] = useState(preset ?? "");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [aliases, setAliases] = useState("");
  const [status, setStatus] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [topic, setTopic] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<BrainFiled | null>(null);
  const [undone, setUndone] = useState(false);
  const creating = project === NEW_PROJECT;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setSaving(true);
    setError(null);
    try {
      let home = project;
      if (creating) {
        const made = await createProject.mutateAsync({
          name,
          summary: purpose,
          aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean),
        });
        home = made.id;
        setProject(made.id);
      }
      const result = await fileIt.mutateAsync({ file, title, description, topic: home ? "" : topic, project: home, status });
      setDone(result);
    } catch (caught) {
      setError(caught);
    } finally {
      setSaving(false);
    }
  }

  async function takeBack() {
    if (!done?.checkpoint_id) return;
    setError(null);
    try {
      await undo.mutateAsync(done.checkpoint_id);
      setUndone(true);
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Add a file to the Brain">
      <form className="card capture" onSubmit={submit}>
        <h2>Add a file to the Brain</h2>
        {done ? (
          <>
            <p>
              {undone
                ? done.replaced
                  ? "Undone: the earlier version is back, and your AI gets that one."
                  : "Taken back out: your AI no longer gets it."
                : done.message}
            </p>
            <ErrorNote error={error} />
            <div className="row">
              {done.status === "pending" ? (
                <Link className="button primary" to="/review" onClick={onClose}>
                  Review it now
                </Link>
              ) : null}
              {done.status === "applied" && done.checkpoint_id && !undone ? (
                <button type="button" onClick={takeBack} disabled={undo.isPending}>
                  Undo
                </button>
              ) : null}
              <button type="button" className={done.status === "pending" ? "" : "primary"} onClick={onClose}>
                Close
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="muted">
              Your AI can use it in its next answer, quoting the part a request is about. File work in its project so
              asking about the project brings it.
            </p>
            <Field label="File" hint="PDF, Word, PowerPoint, Markdown, text or HTML; images, fonts, audio, video, CSV or JSON. Up to 10 MB.">
              <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </Field>
            <Field label="Project" hint="A file named like one already in the project becomes its new version.">
              <select value={project} onChange={(event) => setProject(event.target.value)}>
                <option value="">No project</option>
                {(projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
                <option value={NEW_PROJECT}>New project…</option>
              </select>
            </Field>
            {creating ? (
              <>
                <Field label="Project name">
                  <input value={name} required onChange={(event) => setName(event.target.value)} />
                </Field>
                <Field label="What it is for" hint="One line.">
                  <input value={purpose} required onChange={(event) => setPurpose(event.target.value)} />
                </Field>
                <Field label="Other names you call it" hint="Separated by commas, like: the campaign proposals, Q4 campaign">
                  <input value={aliases} onChange={(event) => setAliases(event.target.value)} />
                </Field>
              </>
            ) : null}
            <Field label="Which copy is this">
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="">Not saying</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title">
              <input value={title} placeholder={file?.name ?? ""} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="What it covers" hint="Optional: one line. Without it, the Brain uses the file's own opening.">
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </Field>
            {project ? null : (
              <Field label="Topic">
                <select value={topic} onChange={(event) => setTopic(event.target.value)}>
                  <option value="">Let the Brain place it</option>
                  {(catalog?.areas ?? []).flatMap((area) =>
                    area.topics.map((t) => (
                      <option key={t.key} value={t.key}>
                        {area.label} / {t.label}
                      </option>
                    )),
                  )}
                </select>
              </Field>
            )}
            <ErrorNote error={error} />
            <div className="row">
              <button type="button" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                className="primary"
                disabled={!file || saving || (creating && (!name.trim() || !purpose.trim()))}
              >
                Add to the Brain
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
