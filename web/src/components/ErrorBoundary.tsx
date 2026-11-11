import { Component, type ErrorInfo, type ReactNode } from "react";
import { CircleAlert, RefreshCw } from "lucide-react";

/** Shows a readable error with a reload button instead of a blank screen when a page crashes. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    // navigating to another page clears the error
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page">
        <div className="callout err" style={{ alignItems: "center" }}>
          <CircleAlert size={20} style={{ color: "var(--err)" }} />
          <div className="grow">
            <div className="strong">Something went wrong on this page</div>
            <div className="small mono" style={{ color: "var(--text-2)" }}>{this.state.error.message}</div>
          </div>
          <button className="btn" onClick={() => window.location.reload()}><RefreshCw size={14} />Reload</button>
        </div>
      </div>
    );
  }
}
