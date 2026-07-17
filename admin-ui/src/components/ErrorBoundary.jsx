import { Component } from "react";
import "./ErrorBoundary.css";

/**
 * Catches rendering errors in the routed page so a crash shows a friendly
 * fallback (with the shell still intact) instead of a fully blank screen.
 * Reset it by changing `resetKey` (we pass the route path in MainLayout), so
 * navigating to another page clears the error automatically.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("Page render error:", error, info);
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" role="alert">
          <div className="error-boundary-chip" aria-hidden="true">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <h2 className="error-boundary-title">Something went wrong on this page</h2>
          <p className="error-boundary-text">
            The page hit an unexpected error and couldn&apos;t render. You can retry, or
            head back to the dashboard.
          </p>
          <div className="error-boundary-actions">
            <button className="btn btn-primary btn-md" onClick={() => this.setState({ hasError: false, error: null })}>
              Try again
            </button>
            <a className="btn btn-secondary btn-md" href="/ui/dashboard">Go to dashboard</a>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
