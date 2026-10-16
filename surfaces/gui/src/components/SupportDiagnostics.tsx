import { Component, type ReactNode } from "react";
import { reportBrowserDiagnostic } from "../api";
import { openSupport } from "../supportFault";

export class SupportErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean; requestId?: string }> {
  state: { failed: boolean; requestId?: string } = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() {
    // Deliberately ignore error and stack: they can contain private provider/input text.
    void reportBrowserDiagnostic("page_crash").then((requestId) => this.setState({ requestId }));
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return <div className="m-auto p-8 max-w-lg text-ink">
      <h1 className="text-xl mb-3">页面暂时遇到问题</h1>
      <p className="text-muted mb-3">可以刷新页面重试，或反馈此问题。不会自动上传输入内容。</p>
      {this.state.requestId && <p className="text-xs break-all mb-3">排查编号：{this.state.requestId}</p>}
      <button className="btn" onClick={() => openSupport(this.state.requestId)}>反馈此问题</button>
      <button className="btn ml-2" onClick={() => window.location.reload()}>刷新页面</button>
    </div>;
  }
}

let installed = false;
export function installSafeBrowserDiagnostics(): void {
  if (installed) return;
  installed = true;
  let previous = 0;
  const report = () => {
    if (Date.now() - previous < 60_000) return;
    previous = Date.now();
    void reportBrowserDiagnostic("page_crash");
  };
  window.addEventListener("error", report);
  window.addEventListener("unhandledrejection", report);
}
