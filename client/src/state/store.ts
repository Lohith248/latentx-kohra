import { create } from "zustand";
import { emptyDraft, missing, toWire, type Draft } from "../orders/draft";
import type { DsHello, DsState, OrderResult, PlayerHello, Radio, Status } from "./types";

export function token(): string {
  return new URLSearchParams(location.search).get("t") ?? "";
}

function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}?t=${encodeURIComponent(token())}`;
}

interface PlayerStore {
  hello: PlayerHello | null;
  msgs: Radio[];
  status: Status | null;
  draft: Draft;
  picking: boolean;
  lastResult: OrderResult | null;
  connected: boolean;
  error: string | null;
  seq: number;
  ws: WebSocket | null;
  connect: () => void;
  setDraft: (p: Partial<Draft>) => void;
  toggleRelied: (id: string) => void;
  setPicking: (v: boolean) => void;
  send: () => void;
}

export const usePlayer = create<PlayerStore>((set, get) => ({
  hello: null, msgs: [], status: null, draft: emptyDraft(), picking: false, lastResult: null,
  connected: false, error: null, seq: 0, ws: null,
  connect: () => {
    const ws = new WebSocket(wsUrl("/ws/play"));
    ws.onopen = () => set({ connected: true, error: null });
    ws.onclose = (e) => set({ connected: false, error: e.code === 4403 ? "Access refused: check the player link." : "Disconnected from server." });
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data as string);
      if (f.type === "hello") set({ hello: f });
      else if (f.type === "history") set({ msgs: f.messages });
      else if (f.type === "radio") set((s) => ({ msgs: [...s.msgs, f] }));
      else if (f.type === "status") set({ status: f });
      else if (f.type === "order_result") set({ lastResult: f });
    };
    set({ ws });
  },
  setDraft: (p) => set((s) => ({ draft: { ...s.draft, ...p } })),
  toggleRelied: (id) => set((s) => {
    const has = s.draft.reliedOn.includes(id);
    const reliedOn = has ? s.draft.reliedOn.filter((x) => x !== id) : [...s.draft.reliedOn, id];
    return { draft: { ...s.draft, reliedOn, reliedNone: reliedOn.length ? false : s.draft.reliedNone } };
  }),
  setPicking: (v) => set({ picking: v }),
  send: () => {
    const { draft, ws, seq, hello, status } = get();
    if (!ws || !hello || missing(draft).length || status?.endex) return;
    const netFor = (to: string) => hello.stations.find((s) => s.callsign === to)?.nets.find((n) => hello.nets.some((m) => m.id === n)) ?? "";
    ws.send(JSON.stringify(toWire(draft, seq + 1, netFor)));
    set({ seq: seq + 1, draft: { ...emptyDraft(), to: draft.to }, picking: false });
  },
}));

interface DsStore {
  hello: DsHello | null;
  state: DsState | null;
  error: string | null;
  connect: () => void;
}

export const useDs = create<DsStore>((set) => ({
  hello: null, state: null, error: null,
  connect: () => {
    const ws = new WebSocket(wsUrl("/ws/ds"));
    ws.onclose = (e) => set({ error: e.code === 4403 ? "Access refused: DS token required." : "Disconnected from server." });
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data as string);
      if (f.type === "hello") set({ hello: f });
      else if (f.type === "ds_state") set({ state: f });
    };
  },
}));
