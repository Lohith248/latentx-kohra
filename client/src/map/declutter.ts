// Screen-space spacing for unit symbols (pure, unit-tested).

const SEP_PX = 46;
const RING: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1]];

/** Screen-space offsets that keep unit symbols at least SEP_PX apart at the current zoom. A symbol keeps its true
 *  position unless an earlier one already sits there; then it moves to the nearest free slot on a small ring. */
export function declutter(screen: [number, number][]): [number, number][] {
  const placed: [number, number][] = [];
  return screen.map(([x, y]) => {
    const free = (dx: number, dy: number) => placed.every(([px, py]) => Math.hypot(x + dx - px, y + dy - py) >= SEP_PX);
    let off: [number, number] = [0, 0];
    if (!free(0, 0)) {
      outer: for (const r of [SEP_PX, 2 * SEP_PX]) {
        for (const [ux, uy] of RING) {
          const d: [number, number] = [ux * r, uy * r];
          if (free(d[0], d[1])) { off = d; break outer; }
        }
      }
    }
    placed.push([x + off[0], y + off[1]]);
    return off;
  });
}
