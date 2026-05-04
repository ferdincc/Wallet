import { TrendingUp, BarChart3, AlertCircle, Sparkles, MessageSquare, Database } from 'lucide-react'

interface AgentStatusProps {
  agent: string
  status?: 'active' | 'idle' | 'error'
}

const agentIcons: Record<string, any> = {
  'ChatAgent': MessageSquare,
  'DataAgent': Database,
  'AnalysisAgent': BarChart3,
  'SentimentAgent': TrendingUp,
  'PredictionAgent': Sparkles,
  'RiskAgent': AlertCircle,
}

const agentColors: Record<string, string> = {
  'ChatAgent': 'text-blue-400',
  'DataAgent': 'text-green-400',
  'AnalysisAgent': 'text-purple-400',
  'SentimentAgent': 'text-yellow-400',
  'PredictionAgent': 'text-pink-400',
  'RiskAgent': 'text-red-400',
}

export default function AgentStatus({ agent, status = 'idle' }: AgentStatusProps) {
  const Icon = agentIcons[agent] || MessageSquare
  const color = agentColors[agent] || 'text-slate-400'
  
  const statusColors = {
    active: 'bg-green-500',
    idle: 'bg-slate-500',
    error: 'bg-red-500'
  }

  return (
    <div className="flex items-center space-x-2 px-2 py-1 rounded-lg bg-slate-700/50">
      <Icon className={`w-4 h-4 ${color}`} />
      <span className="text-xs text-slate-300">{agent}</span>
      <div className={`w-2 h-2 rounded-full ${statusColors[status]}`} />
    </div>
  )
}


















