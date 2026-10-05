import { ackState } from "../state/picture";
import { usePlayer } from "../state/store";
import type { Precedence } from "../state/types";
import { GRID_KINDS, kindsFor, missing, type OrderKind } from "./draft";

const PRECEDENCES: Precedence[] = ["FLASH", "IMMEDIATE", "PRIORITY", "ROUTINE"];

export function OrdersPanel() {
  const hello = usePlayer((s) => s.hello);
  const d = usePlayer((s) => s.draft);
  const set = usePlayer((s) => s.setDraft);
  const picking = usePlayer((s) => s.picking);
  const setPicking = usePlayer((s) => s.setPicking);
  const send = usePlayer((s) => s.send);
  const msgs = usePlayer((s) => s.msgs);
  const result = usePlayer((s) => s.lastResult);
  const endex = usePlayer((s) => s.status?.endex ?? false);
  if (!hello) return null;
  const bn = hello.stations.find((s) => !s.nets.includes(hello.nets[0]?.id ?? ""))?.callsign ?? "ANVIL";
  const todo = missing(d);
  const sent = msgs.filter((m) => m.direction === "out").slice(-4).reverse();
  const isText = d.kind === "TEXT";
  return (
    <section className="orders" data-testid="orders">
      <fieldset disabled={endex}>
        <label>To
          <select value={d.to ?? ""} data-testid="order-to" onChange={(e) => set({ to: e.target.value || null, kind: null, grid: null })}>
            <option value="">— addressee —</option>
            {hello.stations.map((s) => <option key={s.callsign} value={s.callsign}>{s.callsign}</option>)}
          </select>
        </label>
        <label>Order
          <select value={d.kind ?? ""} data-testid="order-kind" onChange={(e) => set({ kind: (e.target.value || null) as OrderKind | null })}>
            <option value="">— order —</option>
            {kindsFor(d.to, bn).map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}
          </select>
        </label>
        {d.kind && GRID_KINDS.includes(d.kind) && (
          <label>Grid
            <button type="button" className={picking ? "picking" : ""} data-testid="pick-grid" onClick={() => setPicking(!picking)}>
              {picking ? "click the map…" : d.grid ? `GR ${d.grid}` : "Pick on map"}
            </button>
          </label>
        )}
        {d.kind === "MOVE" && (
          <label>Speed
            <select value={d.speed} onChange={(e) => set({ speed: e.target.value as "tactical" | "fast" })}>
              <option value="tactical">tactical</option><option value="fast">fast</option>
            </select>
          </label>
        )}
        <label>Precedence
          <select value={d.precedence} onChange={(e) => set({ precedence: e.target.value as Precedence })}>
            {PRECEDENCES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        {isText ? (
          <label className="grow">Text
            <input type="text" maxLength={200} value={d.text} data-testid="order-text" onChange={(e) => set({ text: e.target.value.replace(/[^\x20-\x7E]/g, "") })} />
          </label>
        ) : (
          <>
            <label className={`confidence ${d.confidence === null ? "unset" : ""}`}>
              {d.confidence === null ? "Set confidence" : `Confidence ${d.confidence}%`}
              <input type="range" min={0} max={100} step={5} value={d.confidence ?? 50} data-testid="confidence"
                aria-label="confidence"
                onChange={(e) => set({ confidence: Number(e.target.value) })}
                onPointerUp={(e) => set({ confidence: Number((e.target as HTMLInputElement).value) })}
                onKeyUp={(e) => set({ confidence: Number((e.target as HTMLInputElement).value) })} />
            </label>
            <label className="relied">
              Relied on: {d.reliedOn.length ? `${d.reliedOn.length} message(s)` : d.reliedNone ? "none" : "—"}
              <span><input type="checkbox" data-testid="relied-none" checked={d.reliedNone} disabled={d.reliedOn.length > 0}
                onChange={(e) => set({ reliedNone: e.target.checked })} /> None</span>
            </label>
          </>
        )}
        <button type="button" className="send" data-testid="send" disabled={todo.length > 0} onClick={send}
          title={todo.length ? `Needs: ${todo.join(", ")}` : "Transmit"}>Send</button>
      </fieldset>
      <div className="sent" data-testid="sent">
        {todo.length > 0 && <span className="needs">Needs: {todo.join(", ")}</span>}
        {result && !result.ok && <span className="rejected">Rejected: {result.reason}</span>}
        {sent.map((m) => (
          <div key={m.msg_id} className="sent-row">
            <span className="mono">{m.clock}</span> {m.to}: {m.fields.type === "free" ? "text" : String(m.fields.type ?? "").replace("order_", "").toUpperCase()}{" "}
            <i>{ackState(m, msgs) === "awaiting WILCO" ? "transmitted (awaiting WILCO)" : ackState(m, msgs)}</i>
          </div>
        ))}
      </div>
    </section>
  );
}
