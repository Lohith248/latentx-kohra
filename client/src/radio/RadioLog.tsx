import { useEffect, useRef } from "react";
import { ageText } from "../state/picture";
import { usePlayer } from "../state/store";

export function RadioLog() {
  const msgs = usePlayer((s) => s.msgs);
  const tick = usePlayer((s) => s.status?.tick ?? 0);
  const tickS = usePlayer((s) => s.hello?.tick_seconds ?? 1);
  const relied = usePlayer((s) => s.draft.reliedOn);
  const toggle = usePlayer((s) => s.toggleRelied);
  const endex = usePlayer((s) => s.status?.endex ?? false);
  const bottom = useRef<HTMLDivElement | null>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [msgs.length]);
  return (
    <section className="radio" data-testid="radio-log">
      <h2>Radio log</h2>
      <div className="radio-scroll">
        <table>
          <thead><tr><th title="Relied on">✓</th><th>Time</th><th>Net</th><th>From</th><th>Prec</th><th>Message</th><th>Grade</th><th>Age</th></tr></thead>
          <tbody>
            {msgs.map((m) => (
              <tr key={m.msg_id + m.direction} className={m.direction === "out" ? "out" : ""} data-msg={m.msg_id}>
                <td>{m.direction === "in" && (
                  <input type="checkbox" aria-label={`rely on ${m.msg_id}`} checked={relied.includes(m.msg_id)} disabled={endex}
                    onChange={() => toggle(m.msg_id)} />)}</td>
                <td className="mono">{m.clock}</td>
                <td>{m.net}</td>
                <td>{m.direction === "out" ? `→ ${m.to}` : m.sender}</td>
                <td><span className={`prec prec-${m.precedence}`}>{m.precedence}</span></td>
                <td className="text">{m.text}{m.partial && <span className="partial">PARTIAL</span>}</td>
                <td>{m.grade && <span className="grade" title="reliability / credibility">{m.grade}</span>}</td>
                <td className="mono">{ageText((tick - m.tick) * tickS)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div ref={bottom} />
      </div>
    </section>
  );
}
