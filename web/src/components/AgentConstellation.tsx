import { TEAM } from "./agents";

/**
 * Animated illustration: the six agents orbit the code they build. Links carry flowing
 * dashes and light pulses (messages between agents). Pure SVG + CSS; respects reduced motion.
 * Colours come from CSS variables (via `style`, since SVG attributes can't use var()),
 * so it adapts to the light and dark themes.
 */
export function AgentConstellation({ active }: { active?: string | null }) {
  const W = 640, H = 380, cx = W / 2, cy = H / 2 + 6, rx = 250, ry = 135;
  const pts = TEAM.map((a, i) => {
    const ang = (-90 + i * (360 / TEAM.length)) * (Math.PI / 180);
    return { ...a, x: cx + rx * Math.cos(ang), y: cy + ry * Math.sin(ang) };
  });
  const ring = pts.map((p, i) => {
    const q = pts[(i + 1) % pts.length];
    const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
    return { id: `ring-${i}`, d: `M${p.x},${p.y} Q${mx + (cx - mx) * -0.18},${my + (cy - my) * -0.18} ${q.x},${q.y}`, c: p.color };
  });
  const font = { fontFamily: "Inter, sans-serif" };

  return (
    <svg className="constellation" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Agent team working together">
      <defs>
        <radialGradient id="core-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" style={{ stopColor: "var(--accent)", stopOpacity: 0.5 }} />
          <stop offset=".45" style={{ stopColor: "var(--accent-2)", stopOpacity: 0.16 }} />
          <stop offset="1" style={{ stopColor: "var(--accent-2)", stopOpacity: 0 }} />
        </radialGradient>
        <linearGradient id="core-stroke" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--agent-requirements)" }} />
          <stop offset="1" style={{ stopColor: "var(--agent-architecture)" }} />
        </linearGradient>
        {pts.map((p) => (
          <radialGradient key={p.key} id={`g-${p.key}`} cx="50%" cy="50%" r="50%">
            <stop offset="0" style={{ stopColor: p.color, stopOpacity: 0.45 }} />
            <stop offset="1" style={{ stopColor: p.color, stopOpacity: 0 }} />
          </radialGradient>
        ))}
      </defs>

      {/* orbits */}
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" strokeDasharray="2 7" style={{ stroke: "var(--cl-orbit)" }} />
      <ellipse cx={cx} cy={cy} rx={rx * 0.62} ry={ry * 0.62} fill="none" strokeDasharray="1 9" className="spin-slow"
        style={{ stroke: "var(--cl-orbit-2)", transformOrigin: `${cx}px ${cy}px` }} />

      {/* spokes: agent <-> code */}
      {pts.map((p, i) => {
        const d = `M${p.x},${p.y} L${cx},${cy}`;
        return (
          <g key={`s-${p.key}`}>
            <path id={`spoke-${i}`} d={d} strokeWidth="1.2" fill="none" style={{ stroke: p.color, strokeOpacity: 0.22 }} />
            <path d={d} strokeWidth="1.6" fill="none" className="flow" style={{ stroke: p.color, strokeOpacity: 0.7, animationDelay: `${i * -0.4}s` }} />
            <circle r="3.2" style={{ fill: p.color }}>
              <animateMotion dur={`${2.6 + (i % 3) * 0.5}s`} begin={`${i * 0.45}s`} repeatCount="indefinite"
                keyPoints={i % 2 ? "0;1" : "1;0"} keyTimes="0;1" calcMode="linear">
                <mpath href={`#spoke-${i}`} />
              </animateMotion>
            </circle>
          </g>
        );
      })}

      {/* ring: hand-offs between consecutive agents */}
      {ring.map((r, i) => (
        <g key={r.id}>
          <path id={r.id} d={r.d} strokeWidth="1" fill="none" style={{ stroke: r.c, strokeOpacity: 0.16 }} />
          <circle r="2.4" style={{ fill: r.c, opacity: 0.9 }}>
            <animateMotion dur="4.2s" begin={`${i * 0.7}s`} repeatCount="indefinite"><mpath href={`#${r.id}`} /></animateMotion>
          </circle>
        </g>
      ))}

      {/* core: your code */}
      <circle cx={cx} cy={cy} r="92" fill="url(#core-glow)" className="breathe" style={{ transformOrigin: `${cx}px ${cy}px` }} />
      <g transform={`translate(${cx - 46}, ${cy - 40})`}>
        <rect width="92" height="80" rx="18" stroke="url(#core-stroke)" strokeWidth="1.5" style={{ fill: "var(--cl-core-bg)" }} />
        <text x="46" y="37" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="20" fontWeight="600"
          style={{ fill: "var(--text)" }}>{"</>"}</text>
        <text x="46" y="60" textAnchor="middle" fontSize="11" style={{ ...font, fill: "var(--muted)" }}>your code</text>
      </g>

      {/* agents */}
      {pts.map((p) => {
        const Icon = p.icon;
        const on = active === p.key;
        return (
          <g key={p.key} transform={`translate(${p.x}, ${p.y})`} className={`agent-node ${on ? "on" : ""}`}>
            <circle r="34" fill={`url(#g-${p.key})`} className="breathe" />
            <circle r="23" strokeWidth={on ? 2 : 1.4} style={{ fill: "var(--cl-node-bg)", stroke: p.color, strokeOpacity: on ? 1 : 0.7 }} />
            <foreignObject x="-11" y="-11" width="22" height="22">
              <div style={{ color: p.color, display: "grid" }}><Icon size={22} strokeWidth={1.8} /></div>
            </foreignObject>
            <text y="42" textAnchor="middle" fontSize="12" fontWeight="600" style={{ ...font, fill: "var(--text)" }}>{p.name}</text>
            <text y="57" textAnchor="middle" fontSize="10" fontWeight="700" letterSpacing=".08em" style={{ ...font, fill: p.color }}>
              {p.role.toUpperCase()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
