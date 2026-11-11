import { TEAM } from "./agents";

/**
 * Animated illustration: the six agents orbit the code they build. Links carry flowing
 * dashes and light pulses (messages between agents). Pure SVG + CSS; respects reduced motion.
 */
export function AgentConstellation({ active }: { active?: string | null }) {
  const W = 640, H = 380, cx = W / 2, cy = H / 2 + 6, rx = 250, ry = 135;
  const pts = TEAM.map((a, i) => {
    const ang = (-90 + i * (360 / TEAM.length)) * (Math.PI / 180);
    return { ...a, x: cx + rx * Math.cos(ang), y: cy + ry * Math.sin(ang) };
  });
  const ring = pts.map((p, i) => {
    const q = pts[(i + 1) % pts.length];
    return { id: `ring-${i}`, d: `M${p.x},${p.y} Q${(p.x + q.x) / 2 + (cx - (p.x + q.x) / 2) * -0.18},${(p.y + q.y) / 2 + (cy - (p.y + q.y) / 2) * -0.18} ${q.x},${q.y}`, c: p.color };
  });

  return (
    <svg className="constellation" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Agent team working together">
      <defs>
        <radialGradient id="core-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#34d399" stopOpacity=".55" />
          <stop offset=".45" stopColor="#10b981" stopOpacity=".18" />
          <stop offset="1" stopColor="#10b981" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="core-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#10241a" />
          <stop offset="1" stopColor="#08140e" />
        </linearGradient>
        <linearGradient id="core-stroke" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#a3e635" />
          <stop offset="1" stopColor="#2dd4bf" />
        </linearGradient>
        {pts.map((p) => (
          <radialGradient key={p.key} id={`g-${p.key}`} cx="50%" cy="50%" r="50%">
            <stop offset="0" stopColor={p.color} stopOpacity=".45" />
            <stop offset="1" stopColor={p.color} stopOpacity="0" />
          </radialGradient>
        ))}
      </defs>

      {/* orbit */}
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#23402f" strokeDasharray="2 7" />
      <ellipse cx={cx} cy={cy} rx={rx * 0.62} ry={ry * 0.62} fill="none" stroke="#1b3325" strokeDasharray="1 9" className="spin-slow" style={{ transformOrigin: `${cx}px ${cy}px` }} />

      {/* spokes: agent <-> code */}
      {pts.map((p, i) => {
        const d = `M${p.x},${p.y} L${cx},${cy}`;
        return (
          <g key={`s-${p.key}`}>
            <path id={`spoke-${i}`} d={d} stroke={p.color} strokeOpacity=".22" strokeWidth="1.2" fill="none" />
            <path d={d} stroke={p.color} strokeOpacity=".7" strokeWidth="1.6" fill="none" className="flow" style={{ animationDelay: `${i * -0.4}s` }} />
            <circle r="3.2" fill={p.color} className="pulse-dot">
              <animateMotion dur={`${2.6 + (i % 3) * 0.5}s`} begin={`${i * 0.45}s`} repeatCount="indefinite" keyPoints={i % 2 ? "0;1" : "1;0"} keyTimes="0;1" calcMode="linear">
                <mpath href={`#spoke-${i}`} />
              </animateMotion>
            </circle>
          </g>
        );
      })}

      {/* ring: hand-offs between consecutive agents */}
      {ring.map((r, i) => (
        <g key={r.id}>
          <path id={r.id} d={r.d} stroke={r.c} strokeOpacity=".16" strokeWidth="1" fill="none" />
          <circle r="2.4" fill={r.c} opacity=".9">
            <animateMotion dur="4.2s" begin={`${i * 0.7}s`} repeatCount="indefinite"><mpath href={`#${r.id}`} /></animateMotion>
          </circle>
        </g>
      ))}

      {/* core: your code */}
      <circle cx={cx} cy={cy} r="92" fill="url(#core-glow)" className="breathe" style={{ transformOrigin: `${cx}px ${cy}px` }} />
      <g transform={`translate(${cx - 46}, ${cy - 40})`}>
        <rect width="92" height="80" rx="18" fill="url(#core-fill)" stroke="url(#core-stroke)" strokeWidth="1.5" />
        <text x="46" y="37" textAnchor="middle" fill="#e8eaf0" fontFamily="JetBrains Mono, monospace" fontSize="20" fontWeight="600">{"</>"}</text>
        <text x="46" y="60" textAnchor="middle" fill="#88a395" fontFamily="Inter, sans-serif" fontSize="11">your code</text>
      </g>

      {/* agents */}
      {pts.map((p) => {
        const Icon = p.icon;
        const on = active === p.key;
        return (
          <g key={p.key} transform={`translate(${p.x}, ${p.y})`} className={`agent-node ${on ? "on" : ""}`}>
            <circle r="34" fill={`url(#g-${p.key})`} className="breathe" />
            <circle r="23" fill="#0b1610" stroke={p.color} strokeOpacity={on ? 1 : 0.65} strokeWidth={on ? 2 : 1.4} />
            <foreignObject x="-11" y="-11" width="22" height="22"><Icon size={22} color={p.color} strokeWidth={1.8} /></foreignObject>
            <text y="42" textAnchor="middle" fill="#e8eaf0" fontFamily="Inter, sans-serif" fontSize="12" fontWeight="600">{p.name}</text>
            <text y="57" textAnchor="middle" fill={p.color} fontFamily="Inter, sans-serif" fontSize="10" fontWeight="600" letterSpacing=".08em">{p.role.toUpperCase()}</text>
          </g>
        );
      })}
    </svg>
  );
}
