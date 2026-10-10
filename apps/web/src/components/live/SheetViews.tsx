// One sheet, three views (UX plan 4.3, BL 8.2): a grid with typed columns (AG Grid Community),
// a board grouped by a status column (dnd-kit) and a calendar placed by a date column
// (FullCalendar's standard edition). Moving a card or an event is a cell write with its history,
// exactly like editing the grid. Values an AI filled are marked until you touch them, old values
// show their age, computed columns are read-only and say what they compute.

import { DndContext, type DragEndEvent, useDraggable, useDroppable } from "@dnd-kit/core";
import type { EventDropArg } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import { AllCommunityModule, type CellValueChangedEvent, type ColDef, ModuleRegistry } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";

import type { SheetView, StateColumn, StateRow } from "../../api/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export type Write = (row: StateRow, values: Record<string, unknown>) => void;

type Line = Record<string, unknown> & { __row: StateRow };

function shown(row: StateRow, column: StateColumn): unknown {
  return column.formula ? row.computed[column.name] : row.cells[column.name]?.value;
}

/** The grid: every column typed, the key and computed columns read-only. */
export function Grid({ view, onWrite, onOpen }: { view: SheetView; onWrite: Write; onOpen: (row: StateRow) => void }) {
  const { sheet } = view;
  const columns = useMemo<ColDef<Line>[]>(
    () =>
      sheet.columns.map((column) => {
        const def: ColDef<Line> = {
          field: column.name,
          headerName: column.name,
          headerTooltip: column.formula_words ? `Computed: ${column.formula_words}` : undefined,
          editable: !column.formula && column.name !== sheet.key,
          cellClassRules: {
            "cell-ai": (p) => !!p.data?.__row.cells[column.name]?.ai,
            "cell-stale": (p) => !!p.data?.__row.cells[column.name]?.stale,
            "cell-computed": () => !!column.formula,
            "cell-waiting": (p) => !!p.data?.__row.pending.some((e) => e.column === column.name),
          },
        };
        if (column.type === "status" && column.options.length) {
          def.cellEditor = "agSelectCellEditor";
          def.cellEditorParams = { values: ["", ...column.options] };
        }
        if (column.type === "date") def.cellEditor = "agDateStringCellEditor";
        if (column.type === "number" || column.type === "money") def.cellEditor = "agNumberCellEditor";
        if (column.name === sheet.key) {
          def.pinned = "left";
          def.onCellClicked = (p) => p.data && onOpen(p.data.__row);
          def.cellClass = "cell-key";
        }
        return def;
      }),
    [sheet, onOpen],
  );
  const lines = useMemo<Line[]>(
    () => view.rows.map((row) => ({ __row: row, ...Object.fromEntries(sheet.columns.map((c) => [c.name, shown(row, c) ?? ""])) })),
    [view.rows, sheet.columns],
  );
  const changed = (event: CellValueChangedEvent<Line>) => {
    const name = event.colDef.field;
    if (!event.data || !name) return;
    onWrite(event.data.__row, { [name]: event.newValue ?? "" });
  };
  return (
    <div className="sheet-grid" role="region" aria-label={`${sheet.title} grid`}>
      <AgGridReact<Line>
        rowData={lines}
        columnDefs={columns}
        domLayout="autoHeight"
        getRowId={(p) => p.data.__row.id}
        onCellValueChanged={changed}
        stopEditingWhenCellsLoseFocus
      />
    </div>
  );
}

/** The status columns a board can group by, and the date columns a calendar can place by. */
export function statusColumns(view: SheetView): StateColumn[] {
  return view.sheet.columns.filter((c) => c.type === "status" && c.options.length && !c.formula);
}
export function dateColumns(view: SheetView): StateColumn[] {
  return view.sheet.columns.filter((c) => c.type === "date" && !c.formula);
}

/** The board: cards grouped by a status column. Drag a card, or use its menu. */
export function Board({ view, by, onWrite, onOpen }: { view: SheetView; by: StateColumn; onWrite: Write; onOpen: (row: StateRow) => void }) {
  const lanes = ["", ...by.options];
  const end = (event: DragEndEvent) => {
    const row = view.rows.find((r) => r.id === event.active.id);
    const lane = event.over?.id;
    if (row && typeof lane === "string" && lane !== String(row.cells[by.name]?.value ?? "")) onWrite(row, { [by.name]: lane });
  };
  return (
    <DndContext onDragEnd={end}>
      <div className="sheet-board" role="region" aria-label={`${view.sheet.title} board by ${by.name}`}>
        {lanes.map((lane) => (
          <Lane key={lane || "none"} id={lane} title={lane ? lane.replaceAll("_", " ") : `No ${by.name}`}>
            {view.rows
              .filter((r) => String(r.cells[by.name]?.value ?? "") === lane)
              .map((row) => (
                <Card key={row.id} row={row} view={view} by={by} lanes={lanes} onWrite={onWrite} onOpen={onOpen} />
              ))}
          </Lane>
        ))}
      </div>
    </DndContext>
  );
}

function Lane({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <section ref={setNodeRef} className={`board-lane${isOver ? " over" : ""}`} aria-label={title}>
      <h3 className="small">{title}</h3>
      {children}
    </section>
  );
}

function Card({
  row,
  view,
  by,
  lanes,
  onWrite,
  onOpen,
}: {
  row: StateRow;
  view: SheetView;
  by: StateColumn;
  lanes: string[];
  onWrite: Write;
  onOpen: (row: StateRow) => void;
}) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: row.id });
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;
  const extra = view.sheet.columns.filter((c) => c.name !== view.sheet.key && c.name !== by.name).slice(0, 2);
  return (
    <article ref={setNodeRef} style={style} className="card board-card" aria-label={row.key}>
      <div className="row">
        <button type="button" className="link" onClick={() => onOpen(row)}>
          {row.key}
        </button>
        <span className="drag-handle" {...listeners} {...attributes} aria-label={`Drag ${row.key}`}>
          ⠿
        </span>
      </div>
      {extra.map((c) =>
        shown(row, c) !== undefined && shown(row, c) !== "" ? (
          <p key={c.name} className="small muted">
            {c.name}: {String(shown(row, c))}
          </p>
        ) : null,
      )}
      <label className="small">
        Move to{" "}
        <select value={String(row.cells[by.name]?.value ?? "")} onChange={(event) => onWrite(row, { [by.name]: event.target.value })}>
          {lanes.map((lane) => (
            <option key={lane || "none"} value={lane}>
              {lane ? lane.replaceAll("_", " ") : "none"}
            </option>
          ))}
        </select>
      </label>
    </article>
  );
}

/** The calendar: rows placed by a date column; moving an event writes that cell. */
export function Calendar({ view, by, onWrite, onOpen }: { view: SheetView; by: StateColumn; onWrite: Write; onOpen: (row: StateRow) => void }) {
  const events = view.rows
    .filter((r) => r.cells[by.name]?.value)
    .map((r) => ({ id: r.id, title: r.key, start: String(r.cells[by.name]?.value), allDay: true }));
  const moved = (arg: EventDropArg) => {
    const row = view.rows.find((r) => r.id === arg.event.id);
    const day = arg.event.startStr.slice(0, 10);
    if (row && day) onWrite(row, { [by.name]: day });
  };
  return (
    <div className="sheet-calendar" role="region" aria-label={`${view.sheet.title} calendar by ${by.name}`}>
      <FullCalendar
        plugins={[dayGridPlugin, interactionPlugin]}
        initialView="dayGridMonth"
        events={events}
        editable
        eventDrop={moved}
        eventClick={(arg) => {
          const row = view.rows.find((r) => r.id === arg.event.id);
          if (row) onOpen(row);
        }}
        height="auto"
      />
      <ul className="small sr-list" aria-label="Dated rows">
        {events.map((e) => (
          <li key={e.id}>
            {e.title}: {e.start}
          </li>
        ))}
      </ul>
    </div>
  );
}
