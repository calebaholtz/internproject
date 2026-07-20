import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { MessageSquare, Shield, LogOut, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { API_URL } from '@/lib/api'
import { useBranding } from '@/lib/useBranding'

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const role = localStorage.getItem('role')
  const [docs, setDocs] = useState<string[]>([])
  const { appName } = useBranding()

  useEffect(() => {
    if (role !== 'admin') return
    fetch(`${API_URL}/admin/documents`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
    })
      .then((r) => r.json())
      .then((d) => setDocs(d.documents.map((doc: { name: string }) => doc.name)))
      .catch(() => {})
  }, [location.pathname])

  function handleLogout() {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  return (
    <div className="flex flex-col h-full w-64 bg-gray-900 text-gray-100 p-4 gap-2">
      <div className="mb-4 flex items-center gap-2.5">
        <div className="bg-white rounded-md p-1.5 shrink-0">
          <img src="/ats-logo.jpg" alt="Company logo" className="h-4 w-auto" />
        </div>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-white leading-tight">{appName}</h1>
          <p className="text-xs text-gray-400">Real Projects. Real Missions. Real Impact.</p>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        <button
          onClick={() => navigate('/chat')}
          className={cn(
            'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left',
            location.pathname === '/chat'
              ? 'bg-accent-600 text-white'
              : 'text-gray-300 hover:bg-gray-800'
          )}
        >
          <MessageSquare className="w-4 h-4" />
          Chat
        </button>

        {role === 'admin' && (
          <button
            onClick={() => navigate('/admin')}
            className={cn(
              'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left',
              location.pathname === '/admin'
                ? 'bg-accent-600 text-white'
                : 'text-gray-300 hover:bg-gray-800'
            )}
          >
            <Shield className="w-4 h-4" />
            Admin Panel
          </button>
        )}
      </nav>

      <div className="mt-4 border-t border-gray-700 pt-4">
        <p className="text-xs text-gray-500 mb-2 px-3">Knowledge Base</p>
        <div className="flex flex-col gap-1">
          {docs.length === 0 && (
            <p className="text-xs text-gray-600 px-3">No documents uploaded</p>
          )}
          {docs.map((doc) => (
            <div key={doc} className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 rounded">
              <FileText className="w-3 h-3 shrink-0" />
              <span className="truncate">{doc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-auto">
        <Button
          variant="ghost"
          className="w-full justify-start text-gray-400 hover:text-white hover:bg-gray-800"
          onClick={handleLogout}
        >
          <LogOut className="w-4 h-4 mr-2" />
          Logout
        </Button>
      </div>
    </div>
  )
}
