import { create } from "zustand";
import { emptyDraft, missing, toWire, type Draft } from "../orders/draft";
import type { DsHello, DsState, OrderResult, PlayerHello, Radio, Status } from "./types";

const RECONNECT_MS = 1500;

const TOKEN_KEY = `kohra-token:${location.pathname}`;
let cached: string | null = null;

/** The link's ?t= token, read once and then removed from the address bar so it does not stay in history or
 *  screenshots. Kept for this tab in sessionStorage so a reload still works. */
export function token(): string {
  if (cached !== null) return cached;
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("t");
  let stored: string | null = null;
  try { stored = sessionStorage.getItem(TOKEN_KEY); } catch { stored = null; }
  cached = fromUrl ?? stored ?? "";
  if (fromUrl !== null) {
    try { sessionStorage.setItem(TOKEN_KEY, fromUrl); } catch { /* private mode: the token lives in memory only */ }
    params.delete("t");
    const q = params.toString();
    history.replaceState(null, "", `${location.pathname}${q ? `?${q}` : ""}${location.hash}`);
  }
  return cached;
}

function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}?t=${encodeURIComponent(token())}`;
}

/** After a reconnect the server resends hello; keep the old object when nothing changed so the map is not rebuilt. */
function same<T>(prev: T | null, next: T): T {
  return prev !== null && JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
}

/** POST to a DS endpoint with the DS token from the page URL. */
export async function dsPost(path: string, body: unknown): Promise<{ ok: boolean; status: number; data: unknown }> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
    body: JSON.stringify(body),
  });
  let data: unknown = null;
  try { data = await r.json(); } catch { data = null; }
  return { ok: r.ok, status: r.status, data };
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
    ws.onclose = (e) => {
      if (e.code === 4403) { set({ connected: false, error: "Access refused: check the player link." }); return; }
      if (get().status?.endex) { set({ connected: false }); return; } // the server may stop after the exercise
      set({ connected: false, error: "Connection lost. Reconnecting…" });
      setTimeout(() => get().connect(), RECONNECT_MS);
    };
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data as string);
      if (f.type === "hello") set((s) => ({ hello: same(s.hello, f) }));
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
    if (!ws || ws.readyState !== WebSocket.OPEN || !hello || missing(draft).length || status?.endex) return;
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

export const useDs = create<DsStore>((set, get) => ({
  hello: null, state: null, error: null,
  connect: () => {
    const ws = new WebSocket(wsUrl("/ws/ds"));
    ws.onopen = () => set({ error: null });
    ws.onclose = (e) => {
      if (e.code === 4403) { set({ error: "Access refused: DS token required." }); return; }
      if (get().state?.endex) return;
      set({ error: "Connection lost. Reconnecting…" });
      setTimeout(() => get().connect(), RECONNECT_MS);
    };
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data as string);
      if (f.type === "hello") set((s) => ({ hello: same(s.hello, f) }));
      else if (f.type === "ds_state") set({ state: f });
    };
  },
}));
