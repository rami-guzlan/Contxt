// The knowledge agent's side panel is open on every page: anything can open it, with a message
// to send or an action to run (a suggestion's Run button, the Brain page's quick strip).

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export interface AgentSeed {
  /** A message to send as soon as the panel opens. */
  message?: string;
  /** An action to run as soon as the panel opens. */
  action?: string;
  /** Distinguishes two seeds with the same text. */
  at: number;
}

interface AgentPanelState {
  open: boolean;
  seed: AgentSeed | null;
  openPanel: (seed?: Omit<AgentSeed, "at">) => void;
  closePanel: () => void;
  takeSeed: () => AgentSeed | null;
}

const Context = createContext<AgentPanelState | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [seed, setSeed] = useState<AgentSeed | null>(null);
  const openPanel = useCallback((next?: Omit<AgentSeed, "at">) => {
    if (next && (next.message || next.action)) setSeed({ ...next, at: Date.now() });
    setOpen(true);
  }, []);
  const closePanel = useCallback(() => setOpen(false), []);
  const takeSeed = useCallback(() => {
    const taken = seed;
    if (taken) setSeed(null);
    return taken;
  }, [seed]);
  const value = useMemo(() => ({ open, seed, openPanel, closePanel, takeSeed }), [open, seed, openPanel, closePanel, takeSeed]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** The panel's state; outside the provider (a test rendering one page), a stand-in that does
 * nothing. */
export function useAgentPanel(): AgentPanelState {
  return (
    useContext(Context) ?? {
      open: false,
      seed: null,
      openPanel: () => undefined,
      closePanel: () => undefined,
      takeSeed: () => null,
    }
  );
}
