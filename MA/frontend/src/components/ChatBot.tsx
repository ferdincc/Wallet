import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, ExternalLink, TrendingUp, BarChart3, AlertCircle, Sparkles } from 'lucide-react'
import { chatApi } from '../services/api'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

interface Message {
  role: 'user' | 'assistant'
  content: string
  agent?: string
  sources?: Array<{ title: string; url: string; type: string }>
  intent?: { action: string; symbol?: string }
}

export default function ChatBot() {
  const { t, locale } = useAppPreferences()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const conversationHistory = messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({ role: m.role, content: m.content }))
        .slice(-9)
      const response = await chatApi.sendMessage({
        message: input,
        conversationHistory,
        locale,
      })
      
      // Extract sources from agent_data
      let sources = []
      if (response.agent_data) {
        if (Array.isArray(response.agent_data.sources)) {
          sources = response.agent_data.sources
        } else if (response.agent_data.sentiment?.sources) {
          sources = response.agent_data.sentiment.sources
        } else if (response.agent_data.technical?.sources) {
          sources = response.agent_data.technical.sources
        }
      }
      
      const assistantMessage: Message = {
        role: 'assistant',
        content: response.response || t('chat.errorEmpty'),
        agent: response.agent_data?.agent || 
               (response.agent_data?.sentiment ? 'SentimentAgent' : 
                response.agent_data?.technical ? 'AnalysisAgent' :
                response.agent_data?.prediction ? 'PredictionAgent' : 'ChatAgent'),
        sources: sources,
        intent: response.intent
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      console.error('Chat error:', error)
      const errorMessage: Message = {
        role: 'assistant',
        content: t('chat.errorNetwork'),
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full bg-slate-800 rounded-lg border border-slate-700">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`flex items-start space-x-2 max-w-[80%] ${
                message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
              }`}
            >
              <div
                className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  message.role === 'user'
                    ? 'bg-primary-600'
                    : 'bg-slate-600'
                }`}
              >
                {message.role === 'user' ? (
                  <User className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-white" />
                )}
              </div>
              <div
                className={`rounded-lg px-4 py-2 ${
                  message.role === 'user'
                    ? 'bg-primary-600 text-white'
                    : 'bg-slate-700 text-slate-200'
                }`}
              >
                {/* Agent Badge */}
                {message.role === 'assistant' && message.agent && (
                  <div className="flex items-center space-x-2 mb-2 pb-2 border-b border-slate-600">
                    <div className="flex items-center space-x-1 text-xs text-slate-400">
                      {message.agent === 'SentimentAgent' && <TrendingUp className="w-3 h-3" />}
                      {message.agent === 'AnalysisAgent' && <BarChart3 className="w-3 h-3" />}
                      {message.agent === 'PredictionAgent' && <Sparkles className="w-3 h-3" />}
                      {message.agent === 'RiskAgent' && <AlertCircle className="w-3 h-3" />}
                      <span className="font-medium">{message.agent}</span>
                    </div>
                  </div>
                )}
                {message.content ? (
                  <p className="whitespace-pre-wrap">{message.content}</p>
                ) : null}
                
                {/* Sources */}
                {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-600">
                    <div className="text-xs text-slate-400 mb-2 font-medium">
                      📚 {t('chat.sourcesLabel')}
                    </div>
                    <div className="space-y-1">
                      {message.sources.slice(0, 3).map((source, idx) => (
                        <a
                          key={idx}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center space-x-1 text-xs text-primary-400 hover:text-primary-300 underline"
                        >
                          <span className="truncate">{source.title || source.url}</span>
                          <ExternalLink className="w-3 h-3 flex-shrink-0" />
                        </a>
                      ))}
                      {message.sources.length > 3 && (
                        <div className="text-xs text-slate-500">
                          {t('chat.moreSources').replace(
                            '{count}',
                            String(message.sources.length - 3),
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="flex items-start space-x-2">
              <div className="w-8 h-8 rounded-full bg-slate-600 flex items-center justify-center">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div className="bg-slate-700 rounded-lg px-4 py-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-700 p-4">
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={t('page.dashboard.chatPlaceholder')}
            className="flex-1 bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="bg-primary-600 text-white rounded-lg px-4 py-2 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

