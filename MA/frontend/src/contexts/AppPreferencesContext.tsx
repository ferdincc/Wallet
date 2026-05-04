import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { translate, readStoredLocale, type Locale } from '../i18n/messages'

type AppPreferencesContextValue = {
  /** Her zaman `'en'` — geriye dönük uyumluluk için tutulur */
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: string) => string
}

const AppPreferencesContext = createContext<AppPreferencesContextValue | null>(null)

export function AppPreferencesProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale)

  const setLocale = useCallback((_l: Locale) => {
    setLocaleState('en')
  }, [])

  const t = useCallback((key: string) => translate(locale, key), [locale])

  useEffect(() => {
    document.documentElement.lang = 'en'
  }, [locale])

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t])

  return <AppPreferencesContext.Provider value={value}>{children}</AppPreferencesContext.Provider>
}

export function useAppPreferences(): AppPreferencesContextValue {
  const ctx = useContext(AppPreferencesContext)
  if (!ctx) {
    throw new Error('useAppPreferences must be used within AppPreferencesProvider')
  }
  return ctx
}
