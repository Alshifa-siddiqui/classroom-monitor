import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('UI error boundary caught:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="login-wrap">
          <div className="login-card">
            <h1>Something went wrong</h1>
            <p className="login-sub">{String(this.state.error?.message || this.state.error)}</p>
            <button className="btn primary" onClick={() => window.location.reload()}>
              Reload dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
