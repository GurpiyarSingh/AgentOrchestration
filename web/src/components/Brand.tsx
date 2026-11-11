/** Codeloom brand: woven-threads mark + wordmark. */

export const PRODUCT = { name: "Codeloom", tagline: "Your AI software team" };

export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-label="Codeloom">
      <defs>
        <linearGradient id="cl-a" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a3e635" />
          <stop offset=".55" stopColor="#10b981" />
          <stop offset="1" stopColor="#2dd4bf" />
        </linearGradient>
        <radialGradient id="cl-core" cx="50%" cy="50%" r="50%">
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#bbf7d0" />
        </radialGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" fill="#07100b" stroke="url(#cl-a)" strokeOpacity=".55" />
      {/* woven threads */}
      <path d="M9 14c7 0 7 12 14 12s7-12 9-12" stroke="url(#cl-a)" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M9 26c7 0 7-12 14-12s7 12 9 12" stroke="url(#cl-a)" strokeWidth="2.2" strokeLinecap="round" opacity=".75" />
      <circle cx="9" cy="14" r="2.3" fill="#a3e635" />
      <circle cx="9" cy="26" r="2.3" fill="#34d399" />
      <circle cx="32" cy="14" r="2.3" fill="#38bdf8" />
      <circle cx="32" cy="26" r="2.3" fill="#2dd4bf" />
      <circle cx="20.5" cy="20" r="3" fill="url(#cl-core)" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <div className="brand">
      <div className="brand-mark-wrap"><LogoMark size={32} /></div>
      <div>
        <div className="brand-name">{PRODUCT.name}</div>
        <div className="brand-sub">{PRODUCT.tagline}</div>
      </div>
    </div>
  );
}
