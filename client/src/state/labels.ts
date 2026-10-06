// Plain-language labels shared by the player and DS views (pure, unit-tested).

/** Admiralty grade (reliability A–F, credibility 1–6) to a colour band; the worse of the two decides. */
export function gradeBand(grade: string): "good" | "doubt" | "poor" {
  const rel = "ABCDEF".indexOf(grade[0] ?? "");
  const cred = Number(grade.slice(1)) - 1;
  const worst = Math.max(rel, Number.isFinite(cred) ? cred : 0);
  return worst <= 1 ? "good" : worst === 2 ? "doubt" : "poor";
}

/** Link quality in words, using the same bands as the DS map colours. */
export function sinrWord(sinrDb: number, thetaDb: number): "OK" | "degraded" | "jammed" {
  return sinrDb >= thetaDb + 3 ? "OK" : sinrDb >= thetaDb ? "degraded" : "jammed";
}

/** "FIRE_MISSION" -> "Fire mission". */
export function orderName(kind: string): string {
  const t = kind.replace(/_/g, " ").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}
