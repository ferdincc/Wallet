import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AppPreferencesProvider } from './contexts/AppPreferencesContext'
import { WalletAnalysisProvider } from './contexts/WalletAnalysisContext'
import Wallet from './pages/Wallet'
import Layout from './components/Layout'

function App() {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
    <AppPreferencesProvider>
    <WalletAnalysisProvider>
    <Router>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <Routes>
        <Route path="/wallet" element={<Layout><Wallet /></Layout>} />
        <Route path="/" element={<Navigate to="/wallet" replace />} />
        <Route path="*" element={<Navigate to="/wallet" replace />} />
      </Routes>
      </div>
    </Router>
    </WalletAnalysisProvider>
    </AppPreferencesProvider>
    </div>
  )
}

export default App

