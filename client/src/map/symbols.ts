// Unit symbols and fictional place labels as canvas images (no glyphs needed by the style).
import ms from "milsymbol";

export interface Img { width: number; height: number; data: Uint8ClampedArray; anchor: [number, number] }

function toImg(c: HTMLCanvasElement, anchor: [number, number]): Img {
  const ctx = c.getContext("2d")!;
  return { width: c.width, height: c.height, data: ctx.getImageData(0, 0, c.width, c.height).data, anchor };
}

export function unitImage(sidc: string, mods: Record<string, string>, size = 26): Img {
  const sym = new ms.Symbol(sidc, { size, ...mods });
  const c = sym.asCanvas(window.devicePixelRatio > 1 ? 2 : 1) as HTMLCanvasElement;
  const a = sym.getAnchor();
  const k = c.width / sym.getSize().width;
  return toImg(c, [a.x * k, a.y * k]);
}

export function labelImage(text: string, color = "#1f2a1b"): Img {
  const scale = window.devicePixelRatio > 1 ? 2 : 1;
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d")!;
  const font = `600 ${12 * scale}px system-ui, sans-serif`;
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 8 * scale;
  c.width = w;
  c.height = 18 * scale;
  ctx.font = font;
  ctx.lineWidth = 3 * scale;
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.strokeText(text, 4 * scale, c.height / 2);
  ctx.fillText(text, 4 * scale, c.height / 2);
  return toImg(c, [w / 2, c.height / 2]);
}
