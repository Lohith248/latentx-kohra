import { useEffect } from "react";
import { PlayMap } from "./map/PlayMap";
import { OrdersPanel } from "./orders/OrdersPanel";
import { RadioLog } from "./radio/RadioLog";
import { sinceText } from "./state/picture";
import { usePlayer } from "./state/store";

function TopBar() {
  const hello = usePlayer((s) => s.hello);
  const status = usePlayer((s) => s.status);
  if (!hello) return null;
  const tick = status?.tick ?? 0;
  return (
    <header className="topbar">
      <span className="title">KOHRA · {hello.title} · {hello.callsign}</span>
      <span className="clock" data-testid="clock">{status?.clock ?? "--:--:--"}</span>
      <span className="classif">{hello.classification}</span>
      {hello.synthetic && <span className="synthetic" data-testid="synthetic">SYNTHETIC TERRAIN</span>}
      {status?.paused && !status.endex && <span className="paused" data-testid="paused">PAUSED</span>}
      <span className="heard" data-testid="last-heard">
        {hello.stations.map((s) => (
          <span key={s.callsign} className="heard-item">{s.callsign} <b>{sinceText(tick, status?.last_heard[s.callsign], hello.tick_seconds)}</b></span>
        ))}
      </span>
    </header>
  );
}

export function PlayApp() {
  const connect = usePlayer((s) => s.connect);
  const error = usePlayer((s) => s.error);
  const hello = usePlayer((s) => s.hello);
  const status = usePlayer((s) => s.status);
  useEffect(() => { connect(); }, [connect]);
  if (error && !hello) return <div className="fatal">{error}</div>;
  return (
    <div className="play">
      <TopBar />
      {status?.endex && (
        <div className="endex-banner" data-testid="endex">ENDEX. Inputs locked. Final state hash <code>{status.final_hash}</code></div>
      )}
      {error && hello && <div className="endex-banner warn">{error}</div>}
      <main className="play-body">
        <PlayMap />
        <RadioLog />
      </main>
      <OrdersPanel />
    </div>
  );
}
