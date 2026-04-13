'use client';

import { Component, ReactNode } from 'react';

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: '2rem', fontFamily: 'monospace', background: '#0d1117',
          color: '#e6edf3', minHeight: '100vh',
        }}>
          <h2 style={{ color: '#ff7b72', marginBottom: '1rem' }}>Runtime Error</h2>
          <pre style={{
            background: '#161b22', padding: '1rem', borderRadius: '8px',
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: '13px',
          }}>
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
