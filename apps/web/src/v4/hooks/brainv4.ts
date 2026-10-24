// Data for the v4 Brain items (spec section 6): the Brain map card, the Lore shelf, section
// addresses, session search and the pull budget. Each mirrors a route in
// apps/server/src/workspace_server/routes/release1.py.

import { useMutation, useQuery } from "@tanstack/react-query";

import { get, post, query } from "../../api/client";
import { useRefresh } from "../api";

export type Level = "canon" | "confirmed" | "kept" | "tentative" | "exhaust";

export const LEVELS: Level[] = ["canon", "confirmed", "kept", "tentative", "exhaust"];

/** How each level reads, with the glyph the design gives it. */
export const LEVEL_LABEL: Record<Level, string> = {
  canon: "▲▲ canon",
  confirmed: "▲ confirmed",
  kept: "kept, not verified",
  tentative: "~ tentative",
  exhaust: "▽ exhaust",
};

export interface MapArea {
  id: string;
  name: string;
  covers: string;
  notes: number;
}

export interface MapProject {
  id: string;
  name: string;
  aka: string[];
  status: string;
  address: string;
}

export interface MapSheet {
  id: string;
  name: string;
  columns: string[];
}

export interface MapNamed {
  id: string;
  name: string;
  address?: string;
}

/** GET /api/brain/map/view: every tier whole, and the short map exactly as sent. */
export interface MapView {
  areas: MapArea[];
  projects: MapProject[];
  sheets: MapSheet[];
  must_holds: MapNamed[];
  lore: MapNamed[];
  levels: Partial<Record<Level, number>>;
  sealed: number;
  text: string;
  cut: Record<string, number>;
  tokens: number;
  limit: number;
  caps: Record<string, number>;
  fingerprint: string;
}

export const useMapView = () => useQuery({ queryKey: ["brain", "map", "view"], queryFn: () => get<MapView>("/api/brain/map/view") });

export interface Lesson {
  id: string;
  title: string;
  story: string;
  pattern: string;
  words: string[];
  level: Level;
  level_label: string;
  address: string;
  sections: string[];
  added: string;
  scope: string;
}

export const useLore = () => useQuery({ queryKey: ["brain", "lore"], queryFn: () => get<Lesson[]>("/api/brain/lore") });

export function useProposeLesson() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { title: string; story: string; pattern: string; words: string[]; evidence?: string }) =>
      post<{ status: string; proposal_id?: string; message: string }>("/api/brain/lore", body),
    onSuccess: () => refresh("brain"),
  });
}

export interface SectionRow {
  address: string;
  heading: string;
  slug: string;
  tokens: number;
}

export interface Sections {
  id: string;
  kind: "note" | "lesson" | "file";
  name: string;
  sections: SectionRow[];
}

export const useSections = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["brain", "sections", id],
    queryFn: () => get<Sections>(`/api/brain/sections/${encodeURIComponent(id ?? "")}`),
    enabled: Boolean(id),
  });

export interface FoundSession {
  session_id: string;
  date: string;
  last: string;
  app: string;
  did: string;
  requests: string[];
  given: string[];
  receipts: string[];
}

export const useSessionSearch = (q: string) =>
  useQuery({
    queryKey: ["brain", "sessions", "search", q],
    queryFn: () => get<FoundSession[]>(`/api/brain/sessions/search${query({ q })}`),
    enabled: q.trim().length > 1,
  });
