import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./styles.css";
import "./agentic.css";
import "./theme-light.css";
import { ThemeProvider } from "./theme";
import { AppProvider } from "./components/AppContext";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/ui";
import BuildPage from "./pages/Build";
import ProjectsPage from "./pages/Projects";
import AgentsPage from "./pages/Agents";
import ToolsPage from "./pages/Tools";
import ChatPage from "./pages/Chat";
import RunsPage from "./pages/Runs";
import SettingsPage from "./pages/Settings";
import McpPage from "./pages/Mcp";
import SkillsPage from "./pages/Skills";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
    <ToastProvider>
      <AppProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<BuildPage />} />
              <Route path="builds/:runId" element={<BuildPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="projects/:projectId" element={<ProjectsPage />} />
              <Route path="agents" element={<AgentsPage />} />
              <Route path="tools" element={<ToolsPage />} />
              <Route path="mcp" element={<McpPage />} />
              <Route path="skills" element={<SkillsPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="runs" element={<RunsPage />} />
              <Route path="runs/:runId" element={<RunsPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<BuildPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AppProvider>
    </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
);
