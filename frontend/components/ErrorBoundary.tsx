"use client";
import React from "react";

type State = { error: Error | null };

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("UI error:", error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6">
          <div className="bg-white dark:bg-slate-900 border border-red-200 dark:border-red-800 rounded-lg p-6 max-w-lg space-y-3">
            <h1 className="text-lg font-semibold text-red-700 dark:text-red-300">
              화면을 표시할 수 없습니다
            </h1>
            <pre className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
              {this.state.error.message}
            </pre>
            <div className="flex gap-2">
              <button
                onClick={this.reset}
                className="px-3 py-1 bg-brand-700 text-white rounded text-sm"
              >
                다시 시도
              </button>
              <button
                onClick={() => (window.location.href = "/")}
                className="px-3 py-1 border rounded text-sm"
              >
                홈으로
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
