import { useEffect, useRef } from "react";

/**
 * Ambient "agent network": drifting nodes, faint links between neighbours, and pulses of
 * light travelling along links. Low opacity, pointer-events disabled, pauses when the tab
 * is hidden, and renders a single static frame when the OS asks for reduced motion.
 */
const COLORS_DARK = ["#34d399", "#10b981", "#a3e635", "#2dd4bf", "#4ade80", "#5eead4", "#86efac"];
const COLORS_LIGHT = ["#059669", "#047857", "#65a30d", "#0d9488", "#16a34a", "#0f766e", "#15803d"];
const isLight = () => document.documentElement.dataset.theme === "light";

type Node = { x: number; y: number; vx: number; vy: number; r: number; c: string };
type Pulse = { a: number; b: number; t: number; speed: number; c: string };

export function NetworkBackground({ density = 1 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0, last = performance.now();
    let nodes: Node[] = [];
    const pulses: Pulse[] = [];
    const LINK = 170;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.round(Math.min(90, (w * h) / 26000) * density);
      nodes = Array.from({ length: count }, (_, i) => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.12, vy: (Math.random() - 0.5) * 0.12,
        r: Math.random() < 0.12 ? 2.4 : 1.3, c: String(i % COLORS_DARK.length),
      }));
    };

    const neighbours = (i: number) => {
      const out: number[] = [];
      for (let j = 0; j < nodes.length; j++) {
        if (j === i) continue;
        const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
        if (dx * dx + dy * dy < LINK * LINK) out.push(j);
      }
      return out;
    };

    const frame = (now: number) => {
      const dt = Math.min(50, now - last); last = now;
      const light = isLight();
      const palette = light ? COLORS_LIGHT : COLORS_DARK;
      const col = (c: string) => palette[Number(c)] ?? palette[0];
      ctx.clearRect(0, 0, w, h);

      for (const n of nodes) {
        n.x += n.vx * dt * 0.06 * 16; n.y += n.vy * dt * 0.06 * 16;
        if (n.x < -20) n.x = w + 20; if (n.x > w + 20) n.x = -20;
        if (n.y < -20) n.y = h + 20; if (n.y > h + 20) n.y = -20;
      }
      // links
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
          if (d2 > LINK * LINK) continue;
          const alpha = (1 - Math.sqrt(d2) / LINK) * (light ? 0.22 : 0.16);
          ctx.strokeStyle = light ? `rgba(4, 120, 87, ${alpha})` : `rgba(52, 211, 153, ${alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      // spawn pulses ("messages between agents")
      if (!reduce && pulses.length < 14 && Math.random() < 0.06 && nodes.length) {
        const a = Math.floor(Math.random() * nodes.length);
        const nb = neighbours(a);
        if (nb.length) pulses.push({ a, b: nb[Math.floor(Math.random() * nb.length)], t: 0, speed: 0.0008 + Math.random() * 0.0012, c: nodes[a].c });
      }
      for (let k = pulses.length - 1; k >= 0; k--) {
        const p = pulses[k];
        p.t += p.speed * dt;
        const a = nodes[p.a], b = nodes[p.b];
        if (p.t >= 1 || !a || !b) { pulses.splice(k, 1); continue; }
        const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const g = ctx.createRadialGradient(x, y, 0, x, y, 10);
        g.addColorStop(0, col(p.c)); g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.globalAlpha = 0.85; ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      }
      // nodes
      for (const n of nodes) {
        ctx.fillStyle = col(n.c);
        ctx.globalAlpha = n.r > 2 ? 0.7 : 0.45;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
        if (n.r > 2) {
          ctx.globalAlpha = 0.12;
          ctx.beginPath(); ctx.arc(n.x, n.y, 8, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame);
    };

    const onVisible = () => { if (!document.hidden && !reduce) { last = performance.now(); cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); } };
    resize();
    raf = requestAnimationFrame(frame);
    const ro = new ResizeObserver(() => { resize(); if (reduce) frame(performance.now()); });
    ro.observe(canvas);
    document.addEventListener("visibilitychange", onVisible);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener("visibilitychange", onVisible); };
  }, [density]);

  return <canvas ref={ref} className="net-bg" aria-hidden="true" />;
}
