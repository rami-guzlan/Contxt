// The doc editor: rich text, saved as Markdown, so a model reads and writes a doc as it is.
// Headings, lists, checklists, quotes, code, links and tables; undo and redo. Loaded only on a
// doc's page (React.lazy), so the rest of the app stays small.

import { TableKit } from "@tiptap/extension-table";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { Placeholder } from "@tiptap/extensions";
import { Markdown } from "@tiptap/markdown";
import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";

export interface RichEditorHandle {
  /** Put Markdown where the cursor is (or in place of the selection). */
  insert: (markdown: string) => void;
  /** The doc as Markdown now. */
  markdown: () => string;
}

export default function RichEditor({
  markdown,
  onChange,
  onSelection,
  label,
  resetKey,
  editable = true,
  handle,
}: {
  markdown: string;
  onChange: (markdown: string) => void;
  onSelection?: (text: string) => void;
  label: string;
  /** Changing it reloads `markdown` into the editor: a restored version, an accepted change. */
  resetKey?: string | number;
  editable?: boolean;
  handle?: Ref<RichEditorHandle>;
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ link: { openOnClick: false, autolink: true } }),
      TaskList,
      TaskItem.configure({ nested: true }),
      TableKit,
      Placeholder.configure({ placeholder: "Write here, or ask the AI on the right…" }),
      Markdown,
    ],
    content: markdown,
    contentType: "markdown",
    editable,
    immediatelyRender: true,
    onUpdate: ({ editor: current }) => onChange(current.getMarkdown()),
    onSelectionUpdate: ({ editor: current }) => {
      const { from, to } = current.state.selection;
      onSelection?.(from === to ? "" : current.state.doc.textBetween(from, to, "\n"));
    },
    editorProps: { attributes: { "aria-label": label, class: "rich-text", role: "textbox", "aria-multiline": "true" } },
  });

  // TipTap can hand out an instance it destroys a moment later (while the page mounts): every
  // use below checks it is still alive.
  const live = editor && !editor.isDestroyed ? editor : null;
  const applied = useRef(resetKey);
  useEffect(() => {
    // A new version came in from outside: show it without counting it as an edit. `markdown`
    // is read only when resetKey changes: while the person types, the text is theirs.
    if (!live || resetKey === applied.current) return;
    applied.current = resetKey;
    live.commands.setContent(markdown, { contentType: "markdown", emitUpdate: false });
  }, [live, resetKey]);

  useEffect(() => {
    if (live && live.isEditable !== editable) live.setEditable(editable);
  }, [live, editable]);

  useImperativeHandle(
    handle,
    () => ({
      insert: (text: string) => {
        if (live && !live.isDestroyed) live.chain().focus().insertContent(text, { contentType: "markdown" }).run();
      },
      markdown: () => (live && !live.isDestroyed ? live.getMarkdown() : markdown),
    }),
    [live, markdown],
  );

  return (
    <div className="rich-editor">
      {live && editable ? <Toolbar editor={live} /> : null}
      <EditorContent editor={live} />
    </div>
  );
}

const IDLE = {
  bold: false,
  italic: false,
  h1: false,
  h2: false,
  h3: false,
  bullets: false,
  numbers: false,
  tasks: false,
  quote: false,
  code: false,
  link: false,
  undo: false,
  redo: false,
};

function Toolbar({ editor }: { editor: Editor }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => (e.isDestroyed ? IDLE : {
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      h1: e.isActive("heading", { level: 1 }),
      h2: e.isActive("heading", { level: 2 }),
      h3: e.isActive("heading", { level: 3 }),
      bullets: e.isActive("bulletList"),
      numbers: e.isActive("orderedList"),
      tasks: e.isActive("taskList"),
      quote: e.isActive("blockquote"),
      code: e.isActive("codeBlock"),
      link: e.isActive("link"),
      undo: e.can().undo(),
      redo: e.can().redo(),
    }),
  });
  const run = (action: (chain: ReturnType<Editor["chain"]>) => ReturnType<Editor["chain"]>) => () =>
    action(editor.chain().focus()).run();

  function link() {
    const current = editor.getAttributes("link").href as string | undefined;
    const href = window.prompt("Link to", current ?? "https://");
    if (href === null) return;
    if (!href.trim()) editor.chain().focus().unsetLink().run();
    else editor.chain().focus().extendMarkRange("link").setLink({ href: href.trim() }).run();
  }

  const buttons: [string, string, boolean, () => void, boolean?][] = [
    ["B", "Bold", state.bold, run((c) => c.toggleBold())],
    ["I", "Italic", state.italic, run((c) => c.toggleItalic())],
    ["H1", "Heading 1", state.h1, run((c) => c.toggleHeading({ level: 1 }))],
    ["H2", "Heading 2", state.h2, run((c) => c.toggleHeading({ level: 2 }))],
    ["H3", "Heading 3", state.h3, run((c) => c.toggleHeading({ level: 3 }))],
    ["•", "Bulleted list", state.bullets, run((c) => c.toggleBulletList())],
    ["1.", "Numbered list", state.numbers, run((c) => c.toggleOrderedList())],
    ["☐", "Checklist", state.tasks, run((c) => c.toggleTaskList())],
    ["❝", "Quote", state.quote, run((c) => c.toggleBlockquote())],
    ["{ }", "Code block", state.code, run((c) => c.toggleCodeBlock())],
    ["🔗", "Link", state.link, link],
    ["▦", "Table", false, run((c) => c.insertTable({ rows: 3, cols: 3, withHeaderRow: true }))],
    ["↶", "Undo", false, run((c) => c.undo()), !state.undo],
    ["↷", "Redo", false, run((c) => c.redo()), !state.redo],
  ];
  return (
    <div className="rich-toolbar" role="toolbar" aria-label="Formatting">
      {buttons.map(([text, name, active, onClick, disabled]) => (
        <button
          key={name}
          type="button"
          title={name}
          aria-label={name}
          aria-pressed={active}
          disabled={disabled}
          className={active ? "tool active" : "tool"}
          onMouseDown={(event) => event.preventDefault()}
          onClick={onClick}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
