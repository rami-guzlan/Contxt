// The quickest ways to bring something into the Brain: talk, upload, or write. Everything lands
// in Capture first, private to you, until you pull from it or file it.

import { NotebookPen } from "lucide-react";
import { useNavigate } from "react-router";

import { useBringIn, useCreateNote } from "../api/hooks";
import { UploadButton } from "./CaptureParts";
import { TalkButton } from "./Talk";
import { ErrorNote } from "./ui";

export function BringIn() {
  const create = useCreateNote();
  const bring = useBringIn();
  const navigate = useNavigate();
  return (
    <section className="bring-in" aria-label="Bring something in" data-tour="home-bring-in">
      <h2>Bring something in</h2>
      <p className="muted">
        Hold the button or Space to talk to your Brain, bring in a recording, a transcript or a file, or write a note. It stays private in
        Capture until you pull from it.
      </p>
      <div className="row">
        <TalkButton big />
        <UploadButton
          busy={bring.isPending}
          onFiles={(files) => {
            const list = Array.from(files);
            void Promise.allSettled(list.map((file) => bring.mutateAsync({ file }))).then((done) => {
              const first = done[0];
              if (list.length === 1 && first?.status === "fulfilled") navigate(`/capture/${encodeURIComponent(first.value.id)}`);
            });
          }}
        />
        <button
          type="button"
          disabled={create.isPending}
          onClick={() => create.mutate({}, { onSuccess: (note) => navigate(`/capture/${note.id}`) })}
        >
          <NotebookPen className="button-icon" aria-hidden="true" />
          Write
        </button>
      </div>
      <ErrorNote error={create.error ?? bring.error} />
    </section>
  );
}
