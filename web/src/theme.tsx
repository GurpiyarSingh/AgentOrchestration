import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/** Light / dark / follow-the-OS theme, stored per browser and applied as <html data-theme>. */
export type ThemePref = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const KEY = "codeloom-theme";
const media = () => window.matchMedia("(prefers-color-scheme: light)");

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "dark";
  } catch {
    return "dark";
  }
}

const resolve = (pref: ThemePref): ResolvedTheme => (pref === "system" ? (media().matches ? "light" : "dark") : pref);

function apply(theme: ResolvedTheme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f2f7f4" : "#050a08");
}

interface ThemeState { pref: ThemePref; theme: ResolvedTheme; setPref: (p: ThemePref) => void; toggle: () => void }
const Ctx = createContext<ThemeState>({ pref: "dark", theme: "dark", setPref: () => {}, toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(readPref);
  const [theme, setTheme] = useState<ResolvedTheme>(() => resolve(readPref()));

  useEffect(() => {
    const t = resolve(pref);
    setTheme(t);
    apply(t);
    if (pref !== "system") return;
    const mq = media();
    const onChange = () => { const r = resolve("system"); setTheme(r); apply(r); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  const setPref = useCallback((p: ThemePref) => {
    try { localStorage.setItem(KEY, p); } catch { /* private mode: keep in memory */ }
    setPrefState(p);
  }, []);
  const toggle = useCallback(() => setPref(theme === "dark" ? "light" : "dark"), [theme, setPref]);

  return <Ctx.Provider value={{ pref, theme, setPref, toggle }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
