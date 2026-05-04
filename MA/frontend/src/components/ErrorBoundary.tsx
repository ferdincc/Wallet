import { Component, ErrorInfo, ReactNode } from 'react'
import { readStoredLocale, translate } from '../i18n/messages'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const stack = error?.stack ?? String(error)
    console.error('[OKYISS ErrorBoundary]', error?.message ?? error, '\n', stack)
    if (errorInfo?.componentStack) {
      console.error('[OKYISS ErrorBoundary] componentStack:', errorInfo.componentStack)
    }
  }

  public render() {
    if (this.state.hasError) {
      const loc = readStoredLocale()
      const t = (key: string) => translate(loc, key)
      return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
          <div className="bg-slate-800 rounded-lg p-6 border border-red-500 max-w-md w-full">
            <h2 className="text-xl font-bold text-red-500 mb-4">{t('errorBoundary.title')}</h2>
            <p className="text-slate-300 mb-4">{t('errorBoundary.body')}</p>
            {this.state.error && (
              <details className="mb-4">
                <summary className="text-sm text-slate-400 cursor-pointer mb-2">
                  {t('errorBoundary.details')}
                </summary>
                <pre className="text-xs text-slate-500 bg-slate-900 p-2 rounded overflow-auto whitespace-pre-wrap break-words">
                  {this.state.error?.stack ?? this.state.error.toString()}
                </pre>
              </details>
            )}
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="w-full bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
            >
              {t('errorBoundary.reload')}
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary












