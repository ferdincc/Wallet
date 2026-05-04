import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

export interface WalletSnapshotPayload {
  address: string
  llmContext: string
  raw: unknown
}

type WalletCtx = {
  walletAddress: string
  walletContextForChat: string
  setWalletAnalysis: (payload: WalletSnapshotPayload) => void
  clearWalletAnalysis: () => void
}

const Ctx = createContext<WalletCtx | null>(null)

/** Adres ve analiz çıktısı yalnızca bellekte; sayfa yenilemede veya sekme kapanınca sıfırlanır (localStorage/sessionStorage yok). */
export function WalletAnalysisProvider({ children }: { children: ReactNode }) {
  const [walletAddress, setWalletAddress] = useState('')
  const [walletContextForChat, setWalletContextForChat] = useState('')

  const setWalletAnalysis = useCallback((payload: WalletSnapshotPayload) => {
    setWalletAddress(payload.address)
    setWalletContextForChat(payload.llmContext)
  }, [])

  const clearWalletAnalysis = useCallback(() => {
    setWalletAddress('')
    setWalletContextForChat('')
  }, [])

  const value = useMemo(
    () => ({
      walletAddress,
      walletContextForChat,
      setWalletAnalysis,
      clearWalletAnalysis,
    }),
    [walletAddress, walletContextForChat, setWalletAnalysis, clearWalletAnalysis],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWalletAnalysis() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useWalletAnalysis must be used within WalletAnalysisProvider')
  return v
}
