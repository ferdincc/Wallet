import { useState, useEffect, useRef } from 'react'
import { Mic, MicOff, VolumeX } from 'lucide-react'
import { voiceApi } from '../services/api'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

interface VoiceAssistantProps {
  onCommandProcessed?: (response: string, agentData?: any) => void
  disabled?: boolean
}

export default function VoiceAssistant({ onCommandProcessed, disabled = false }: VoiceAssistantProps) {
  const { t } = useAppPreferences()
  const speechLang = 'en-US'
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<any>(null)
  const synthesisRef = useRef<SpeechSynthesis | null>(null)
  const onCommandProcessedRef = useRef(onCommandProcessed)
  onCommandProcessedRef.current = onCommandProcessed
  const disabledRef = useRef(disabled)
  disabledRef.current = disabled

  useEffect(() => {
    if (typeof window === 'undefined') return

    synthesisRef.current = window.speechSynthesis

    const speakText = (text: string) => {
      if (!synthesisRef.current || disabledRef.current) return
      try {
        synthesisRef.current.cancel()
      } catch {
        /* ignore */
      }
      const cleanText = text
        .replace(/[^\w\s.,!?;:()\-]/g, '')
        .replace(/\s+/g, ' ')
        .trim()
      if (!cleanText) return
      const utterance = new SpeechSynthesisUtterance(cleanText)
      utterance.lang = speechLang
      utterance.rate = 1.0
      utterance.pitch = 1.0
      utterance.volume = 1.0
      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => setIsSpeaking(false)
      utterance.onerror = () => setIsSpeaking(false)
      synthesisRef.current.speak(utterance)
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

    if (SpeechRecognition) {
      try {
        recognitionRef.current = new SpeechRecognition()
        recognitionRef.current.continuous = false
        recognitionRef.current.interimResults = false
        recognitionRef.current.lang = speechLang

        recognitionRef.current.onresult = async (event: any) => {
          const transcriptText = event.results[0][0].transcript
          setTranscript(transcriptText)
          setIsListening(false)

          try {
            const response = await voiceApi.processCommand(transcriptText)
            if (response.success && response.response) {
              speakText(response.response)
              onCommandProcessedRef.current?.(response.response, response.agent_data)
            }
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : t('voice.commandError')
            setError(msg)
            setIsListening(false)
          }
        }

        recognitionRef.current.onerror = (event: any) => {
          console.error('Speech recognition error:', event.error)
          setError(`${t('voice.recognitionError')} ${event.error}`)
          setIsListening(false)
        }

        recognitionRef.current.onend = () => {
          setIsListening(false)
        }
      } catch (e) {
        console.warn('SpeechRecognition init failed', e)
        setError(t('voice.initFailed'))
      }
    } else {
      setError(t('voice.unsupported'))
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop()
        } catch {
          /* dinleme başlamamışsa stop() InvalidStateError fırlatabilir */
        }
        recognitionRef.current = null
      }
      try {
        synthesisRef.current?.cancel()
      } catch {
        /* ignore */
      }
    }
  }, [speechLang, t])

  const startListening = () => {
    if (disabled || !recognitionRef.current) return
    
    setError(null)
    setTranscript('')
    
    try {
      recognitionRef.current.start()
      setIsListening(true)
    } catch (err: any) {
      setError(`${t('voice.micFailed')} ${err.message}`)
      setIsListening(false)
    }
  }

  const stopListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch {
        /* ignore */
      }
    }
    setIsListening(false)
  }

  const stopSpeaking = () => {
    if (synthesisRef.current) {
      synthesisRef.current.cancel()
      setIsSpeaking(false)
    }
  }

  return (
    <div className="flex flex-col items-center space-y-2">
      <div className="flex items-center space-x-2">
        <button
          onClick={isListening ? stopListening : startListening}
          disabled={disabled || !recognitionRef.current}
          className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
            isListening
              ? 'bg-red-500 hover:bg-red-600 animate-pulse'
              : 'bg-primary-600 hover:bg-primary-700'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          title={isListening ? t('voice.listenStop') : t('voice.listenStart')}
        >
          {isListening ? (
            <MicOff className="w-5 h-5 text-white" />
          ) : (
            <Mic className="w-5 h-5 text-white" />
          )}
        </button>
        
        {isSpeaking && (
          <button
            onClick={stopSpeaking}
            className="w-12 h-12 rounded-full bg-yellow-500 hover:bg-yellow-600 flex items-center justify-center"
            title={t('voice.stopSpeech')}
          >
            <VolumeX className="w-5 h-5 text-white" />
          </button>
        )}
      </div>
      
      {transcript && (
        <div className="text-xs text-slate-400 max-w-xs text-center">
          <div className="font-semibold mb-1">{t('voice.heardTitle')}</div>
          <div className="bg-slate-700 rounded px-2 py-1">{transcript}</div>
        </div>
      )}
      
      {error && (
        <div className="text-xs text-red-400 max-w-xs text-center">
          {error}
        </div>
      )}
      
      {isListening && (
        <div className="text-xs text-primary-400 animate-pulse">
          {t('voice.listening')}
        </div>
      )}
      
      {isSpeaking && (
        <div className="text-xs text-yellow-400 animate-pulse">
          {t('voice.speaking')}
        </div>
      )}
    </div>
  )
}












