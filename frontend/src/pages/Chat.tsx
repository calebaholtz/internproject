import { useState, useRef, useEffect } from 'react'
import { Send, X } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import ChatMessage from '@/components/ChatMessage'
import { API_URL } from '@/lib/api'

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
}

interface Stats {
  cpu_percent: number
  ram_used_gb: number
  ram_total_gb: number
  ram_percent: number
  active_model: string
}

interface BenchmarkResult {
  label: string
  prompt: string
  ttft_s: number | null
  total_s: number | null
  cost: number | null
  peak_cpu: number | null
  avg_cpu: number | null
  peak_ram: number | null
  avg_ram: number | null
  response_preview: string | null
  error: string | null
}

interface BenchmarkData {
  model: string
  ram_percent: number
  results: BenchmarkResult[]
}

const SUGGESTIONS = [
  { label: 'Start the Azure Security Risk Assessment', message: 'start the azure security questionnaire' },
  { label: 'Explain insider threat risks', message: 'explain insider threat risks' },
]

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [ttft, setTtft] = useState<number | null>(null)
  const [totalTime, setTotalTime] = useState<number | null>(null)
  const [benchmarking, setBenchmarking] = useState(false)
  const [benchmark, setBenchmark] = useState<BenchmarkData | null>(null)
  const [lastCost, setLastCost] = useState<number | null>(null)
  const [assessmentActive, setAssessmentActive] = useState(false)
  const [assessmentCompleted, setAssessmentCompleted] = useState(false)
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const pendingTextRef = useRef<string>('')
  const typingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function startTyping(assistantId: number) {
    if (typingIntervalRef.current) return
    typingIntervalRef.current = setInterval(() => {
      if (pendingTextRef.current.length === 0) {
        clearInterval(typingIntervalRef.current!)
        typingIntervalRef.current = null
        return
      }
      const char = pendingTextRef.current[0]
      pendingTextRef.current = pendingTextRef.current.slice(1)
      setMessages((prev) => prev.map((m) =>
        m.id === assistantId ? { ...m, content: m.content + char } : m
      ))
    }, 12)
  }

  useEffect(() => {
    return () => {
      if (typingIntervalRef.current) clearInterval(typingIntervalRef.current)
    }
  }, [])

  const hasMessages = messages.length > 0

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const token = localStorage.getItem('token')
    function fetchStats() {
      fetch(`${API_URL}/debug/stats`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then(setStats)
        .catch(() => {})
    }
    fetchStats()
    const id = setInterval(fetchStats, 2000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput('')
    await sendMessage(text)
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return

    const userMessage: Message = { id: Date.now(), role: 'user', content: text.trim() }
    setMessages((prev) => [...prev, userMessage])
    setLoading(true)
    textareaRef.current?.focus()
    setStreaming(false)
    setTtft(null)
    setTotalTime(null)
    setLastCost(null)
    pendingTextRef.current = ''
    if (typingIntervalRef.current) {
      clearInterval(typingIntervalRef.current)
      typingIntervalRef.current = null
    }
    const sendTime = performance.now()

    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`${API_URL}/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message: userMessage.content }),
      })

      if (!res.ok) throw new Error('Request failed')

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      const assistantId = Date.now() + 1
      let started = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const lines = decoder.decode(value, { stream: true }).split('\n')
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data)
            if (parsed.error) {
              setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: `Error: ${parsed.error}` }])
              started = true
            }
            if (parsed.cost !== undefined) {
              setLastCost(parsed.cost)
            }
            if (parsed.in_assessment !== undefined) {
              setAssessmentActive(parsed.in_assessment)
            }
            if (parsed.assessment_completed) {
              setAssessmentCompleted(true)
            }
            if (parsed.content) {
              if (!started) {
                started = true
                setTtft(parseFloat(((performance.now() - sendTime) / 1000).toFixed(2)))
                setStreaming(true)
                setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '' }])
              }
              pendingTextRef.current += parsed.content
              startTyping(assistantId)
            }
          } catch {}
        }
      }
    } catch {
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Error reaching the server. Make sure the backend is running.' }])
    }

    setTotalTime(parseFloat(((performance.now() - sendTime) / 1000).toFixed(2)))
    setLoading(false)
    setStreaming(false)
  }

  async function previewAssessmentPdf() {
    const token = localStorage.getItem('token')
    const res = await fetch(`${API_URL}/chat/assessment/pdf`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (!res.ok) return
    const blob = await res.blob()
    setPdfPreviewUrl(URL.createObjectURL(blob))
  }

  function closePdfPreview() {
    if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl)
    setPdfPreviewUrl(null)
  }

  useEffect(() => {
    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(e as unknown as React.FormEvent)
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      const el = e.currentTarget
      const start = el.selectionStart
      const end = el.selectionEnd
      const newValue = input.substring(0, start) + '   ' + input.substring(end)
      setInput(newValue)
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = start + 3
      })
    }
  }

  const inputBar = (
    <form onSubmit={handleSend} className="flex items-end gap-3 w-full max-w-2xl">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={assessmentActive ? 'Answer the question above...' : 'How can I help you today?'}
        autoFocus
        rows={1}
        className="flex-1 min-h-[48px] max-h-40 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-colors resize-none overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-track]:my-2 [&::-webkit-scrollbar-thumb]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border-2 [&::-webkit-scrollbar-thumb]:border-transparent [&::-webkit-scrollbar-thumb]:bg-clip-padding"
      />
      <button
        type="submit"
        disabled={loading || !input.trim()}
        className="h-12 w-12 rounded-xl bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
      >
        <Send className="w-4 h-4" />
      </button>
    </form>
  )

  return (
    <div className="flex h-screen bg-[#0c0c10]">
      <Sidebar />

      {stats && (
        <div className="fixed bottom-4 right-4 z-50 rounded-xl border border-white/10 bg-black/70 backdrop-blur-md px-4 py-3 text-xs text-gray-400 space-y-1 font-mono min-w-[260px] max-w-[360px]">
          <div className="text-gray-500 text-[10px] uppercase tracking-wider mb-2">Diagnostics</div>
          <div className="flex justify-between"><span>Model</span><span className="text-white">{stats.active_model.replace(':latest', '')}</span></div>
          <div className="flex justify-between"><span>CPU</span><span className="text-white">{stats.cpu_percent}%</span></div>
          <div className="flex justify-between"><span>RAM</span><span className="text-white">{stats.ram_used_gb} / {stats.ram_total_gb} GB ({stats.ram_percent}%)</span></div>
          {totalTime !== null && <div className="flex justify-between"><span>Response time</span><span className="text-white">{totalTime}s</span></div>}
          {lastCost !== null && <div className="flex justify-between"><span>Last msg cost</span><span className="text-white">{lastCost === 0 ? 'Free' : `$${lastCost.toFixed(6)}`}</span></div>}

          <button
            onClick={async () => {
              setBenchmarking(true)
              setBenchmark(null)
              const token = localStorage.getItem('token')
              try {
                const res = await fetch(`${API_URL}/debug/benchmark`, {
                  method: 'POST',
                  headers: { 'Authorization': `Bearer ${token}` },
                })
                const data = await res.json()
                setBenchmark(data)
              } catch {}
              setBenchmarking(false)
            }}
            disabled={benchmarking}
            className="mt-2 w-full py-1 rounded-lg bg-white/10 hover:bg-white/20 text-gray-300 transition-colors disabled:opacity-50 text-[11px]"
          >
            {benchmarking ? 'Running benchmark...' : 'Run Benchmark'}
          </button>

          {benchmark && (
            <div className="mt-2 space-y-2 border-t border-white/10 pt-2">
              <div className="text-gray-500 text-[10px] uppercase tracking-wider">Results — {benchmark.model.replace(':latest', '')}</div>
              {benchmark.results.map((r) => (
                <div key={r.label} className="space-y-0.5">
                  <div className="text-gray-300 text-[11px] font-semibold">{r.label}</div>
                  {r.error ? (
                    <div className="text-red-400 text-[10px]">{r.error}</div>
                  ) : (
                    <>
                      <div className="flex justify-between"><span>First token</span><span className="text-white">{r.ttft_s}s</span></div>
                      <div className="flex justify-between"><span>Total time</span><span className="text-white">{r.total_s}s</span></div>
                      {r.cost !== null && <div className="flex justify-between"><span>Cost</span><span className="text-white">{r.cost === 0 ? 'Free' : `$${r.cost.toFixed(6)}`}</span></div>}
                      <div className="flex justify-between"><span>Peak CPU</span><span className="text-white">{r.peak_cpu}%</span></div>
                      <div className="flex justify-between"><span>Avg CPU</span><span className="text-white">{r.avg_cpu}%</span></div>
                      <div className="flex justify-between"><span>Peak RAM</span><span className="text-white">{r.peak_ram}%</span></div>
                      <div className="flex justify-between"><span>Avg RAM</span><span className="text-white">{r.avg_ram}%</span></div>
                      <div className="text-gray-600 text-[10px] truncate">{r.response_preview}</div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col flex-1 min-w-0">

        {hasMessages && (
          <div className="flex justify-end items-center gap-4 px-6 py-3 border-b border-white/[0.06]">
            {assessmentCompleted && (
              <button
                onClick={previewAssessmentPdf}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                View PDF Summary
              </button>
            )}
            <button
              onClick={async () => {
                const token = localStorage.getItem('token')
                await fetch(`${API_URL}/chat/clear`, {
                  method: 'POST',
                  headers: { 'Authorization': `Bearer ${token}` },
                })
                setMessages([])
                setTtft(null)
                setTotalTime(null)
                setAssessmentActive(false)
                setAssessmentCompleted(false)
                closePdfPreview()
              }}
              className="text-xs text-gray-500 hover:text-white transition-colors"
            >
              New conversation
            </button>
          </div>
        )}

        {!hasMessages ? (
          /* Centered empty state */
          <div className="flex flex-col flex-1 items-center justify-center px-6 gap-8">
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-indigo-600 mb-4 shadow-lg shadow-indigo-500/20">
                <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h2 className="text-2xl font-semibold text-white mb-2">What do you want to know?</h2>
              <p className="text-sm text-gray-500">Ask anything about the documents in your knowledge base.</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  onClick={() => sendMessage(s.message)}
                  disabled={loading}
                  className="px-4 py-2 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 text-sm text-gray-300 hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {s.label}
                </button>
              ))}
            </div>
            {inputBar}
          </div>
        ) : (
          /* Active chat layout */
          <>
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} role={msg.role} content={msg.content} />
              ))}

              {loading && !streaming && (
                <div className="flex gap-3 mr-auto">
                  <div className="flex-shrink-0 w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-[10px] font-semibold text-gray-400">
                    AI
                  </div>
                  <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white/[0.04] border border-white/[0.08]">
                    <div className="flex gap-1 items-center h-5">
                      <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            <div className="border-t border-white/[0.06] px-6 py-4 flex justify-center">
              {inputBar}
            </div>
          </>
        )}

      </div>

      {pdfPreviewUrl && (
        <div className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="bg-[#0c0c10] border border-white/10 rounded-2xl w-full max-w-3xl h-[85vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 shrink-0">
              <h3 className="text-sm font-semibold text-white">Azure Security Risk Assessment</h3>
              <div className="flex items-center gap-3">
                <a
                  href={pdfPreviewUrl}
                  download="azure-security-assessment.pdf"
                  className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                >
                  Download
                </a>
                <button onClick={closePdfPreview} className="text-gray-400 hover:text-white transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
            <iframe src={pdfPreviewUrl} className="flex-1 w-full bg-white" title="Assessment PDF preview" />
          </div>
        </div>
      )}
    </div>
  )
}
