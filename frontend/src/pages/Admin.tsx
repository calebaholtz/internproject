import { useState, useRef, useEffect } from 'react'
import { Upload, Trash2, FileText, ChevronDown } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { cn } from '@/lib/utils'

interface Doc {
  name: string
  size: string
  uploaded: string
}

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
  }
}

export default function Admin() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [dragging, setDragging] = useState(false)
  const [model, setModel] = useState('llama3.2')
  const [models, setModels] = useState<string[]>([])
  const [guidance, setGuidance] = useState('')
  const [saved, setSaved] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('http://localhost:8000/admin/config', { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => { setModel(d.model); setGuidance(d.guidance) })
      .catch(() => {})

    fetch('http://localhost:8000/admin/models', { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setModels(d.models))
      .catch(() => {})
  }, [])

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file?.name.endsWith('.pdf')) addDoc(file)
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) addDoc(file)
  }

  function addDoc(file: File) {
    setDocs((prev) => [
      { name: file.name, size: `${(file.size / 1024).toFixed(0)} KB`, uploaded: new Date().toISOString().split('T')[0] },
      ...prev,
    ])
  }

  function deleteDoc(name: string) {
    setDocs((prev) => prev.filter((d) => d.name !== name))
  }

  async function handleSaveConfig() {
    try {
      await fetch('http://localhost:8000/admin/config', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ model, guidance }),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {}
  }

  return (
    <div className="flex h-screen bg-[#0c0c10]">
      <Sidebar />

      <div className="flex-1 overflow-y-auto">
        <header className="border-b border-white/[0.06] px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Admin Panel</h2>
          <p className="text-xs text-gray-500 mt-0.5">Manage documents and model configuration</p>
        </header>

        <div className="p-6 space-y-5 max-w-3xl">

          {/* Knowledge Base */}
          <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.06]">
              <h3 className="text-sm font-semibold text-white">Knowledge Base</h3>
              <p className="text-xs text-gray-500 mt-0.5">Upload PDFs to add them to the knowledge base</p>
            </div>

            <div className="p-5 space-y-4">
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                className={cn(
                  'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
                  dragging
                    ? 'border-indigo-500 bg-indigo-500/10'
                    : 'border-white/10 hover:border-white/20 hover:bg-white/[0.02]'
                )}
              >
                <Upload className="w-7 h-7 text-gray-600 mx-auto mb-3" />
                <p className="text-sm font-medium text-gray-400">Drop a PDF here or click to browse</p>
                <p className="text-xs text-gray-600 mt-1">PDF files only</p>
                <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileInput} />
              </div>

              {/* Table */}
              <div className="rounded-lg border border-white/[0.06] overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="border-b border-white/[0.06] bg-white/[0.02]">
                    <tr>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Document</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Uploaded</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {docs.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-gray-600 text-sm">
                          No documents uploaded yet
                        </td>
                      </tr>
                    ) : (
                      docs.map((doc) => (
                        <tr key={doc.name} className="hover:bg-white/[0.02] transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <FileText className="w-3.5 h-3.5 text-gray-600 shrink-0" />
                              <span className="text-gray-300 text-sm">{doc.name}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-gray-500 text-sm">{doc.size}</td>
                          <td className="px-4 py-3 text-gray-500 text-sm font-mono">{doc.uploaded}</td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => deleteDoc(doc.name)}
                              className="text-gray-700 hover:text-red-400 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Config */}
          <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.06]">
              <h3 className="text-sm font-semibold text-white">Model Configuration</h3>
              <p className="text-xs text-gray-500 mt-0.5">Set the Ollama model and system guidance prompt</p>
            </div>

            <div className="p-5 space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">Model</label>
                <div className="relative">
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full h-10 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-white appearance-none focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  >
                    {models.map((m) => {
                      const descriptions: Record<string, string> = {
                        'llama3.2:latest': 'Good for general Q&A, summarization, and conversation',
                        'llama3.2:1b':     'Good for simple questions and short responses',
                        'phi3.5:latest':   'Good for reasoning, coding, and structured answers',
                      }
                      const desc = descriptions[m]
                      const label = m.replace(':latest', '')
                      return (
                        <option key={m} value={m} className="bg-gray-900">
                          {desc ? `${label} — ${desc}` : label}
                        </option>
                      )
                    })}
                  </select>
                  <ChevronDown className="absolute right-3 top-3 w-4 h-4 text-gray-500 pointer-events-none" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">System Guidance</label>
                <textarea
                  value={guidance}
                  onChange={(e) => setGuidance(e.target.value)}
                  rows={4}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none placeholder:text-gray-600"
                />
                <p className="text-xs text-gray-600">Shapes how the AI responds — tone, focus, and constraints.</p>
              </div>

              <button
                onClick={handleSaveConfig}
                className="h-9 px-5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors shadow-lg shadow-indigo-500/20"
              >
                {saved ? 'Saved!' : 'Save Configuration'}
              </button>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
