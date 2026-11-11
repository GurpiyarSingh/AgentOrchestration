import { createContext, useContext, type ReactNode } from "react";
import { api } from "../api";
import { useData } from "../lib";
import type { SettingsView } from "../types";

interface AppState { settings: SettingsView | null; reloadSettings: () => Promise<void>; keyReady: boolean }

const Ctx = createContext<AppState>({ settings: null, reloadSettings: async () => {}, keyReady: false });

export function AppProvider({ children }: { children: ReactNode }) {
  const { data, reload } = useData(api.settings, [], 30000);
  return (
    <Ctx.Provider value={{ settings: data, reloadSettings: reload, keyReady: !!data?.key.configured }}>
      {children}
    </Ctx.Provider>
  );
}

export const useApp = () => useContext(Ctx);
