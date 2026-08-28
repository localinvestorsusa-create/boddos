import * as THREE from 'three';

function baseCanvas(bg: string): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 64;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return { canvas, ctx };
}

function toTexture(canvas: HTMLCanvasElement, repeatX: number): THREE.CanvasTexture {
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.repeat.set(repeatX, 1);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** A scrolling strip of binary digits, seeded so it looks meaningful rather
 * than random noise on every reload. */
export function binaryStripTexture(color: string): THREE.CanvasTexture {
  const { canvas, ctx } = baseCanvas('rgba(0,0,0,0)');
  ctx.fillStyle = color;
  ctx.font = '700 44px "IBM Plex Mono", monospace';
  ctx.textBaseline = 'middle';
  let seed = 1337;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  let x = 0;
  while (x < canvas.width) {
    const bit = rand() > 0.5 ? '1' : '0';
    ctx.fillText(bit, x, canvas.height / 2 + 2);
    x += 30;
  }
  return toTexture(canvas, 6);
}

/** Two rows of odu-style marks: single and paired strokes, the abstract
 * binary vocabulary Ifa divination is built from — not a reproduction of
 * any specific sacred odu, just marks drawn from the same grammar. */
export function oduStripTexture(color: string, variant: 'single' | 'paired'): THREE.CanvasTexture {
  const { canvas, ctx } = baseCanvas('rgba(0,0,0,0)');
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 5;
  ctx.lineCap = 'round';
  let seed = variant === 'single' ? 71 : 409;
  const rand = () => {
    seed = (seed * 48271) % 2147483647;
    return seed / 2147483647;
  };
  let x = 20;
  while (x < canvas.width - 20) {
    const groupWidth = 56;
    const strokes = variant === 'single' ? (rand() > 0.5 ? 1 : 2) : rand() > 0.5 ? 2 : 4;
    for (let i = 0; i < strokes; i++) {
      const sx = x + i * 10;
      ctx.beginPath();
      ctx.moveTo(sx, 14);
      ctx.lineTo(sx, canvas.height - 14);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x + (strokes - 1) * 5, canvas.height / 2, 3, 0, Math.PI * 2);
    ctx.fill();
    x += groupWidth;
  }
  return toTexture(canvas, 5);
}
