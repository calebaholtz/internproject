import { useNavigate, useLocation } from 'react-router-dom'
import { MessageSquare, Shield, LogOut, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const MOCK_DOCS = ['company-policy.pdf', 'onboarding-guide.pdf', 'cve-2024-1234.pdf']

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const role = localStorage.getItem('role')

  function handleLogout() {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  return (
    <div className="flex flex-col h-full w-64 bg-gray-900 text-gray-100 p-4 gap-2">
      <div className="mb-4">
        <h1 className="text-lg font-semibold text-white">DocBot</h1>
        <p className="text-xs text-gray-400">Knowledge Base Assistant</p>
      </div>

      <nav className="flex flex-col gap-1">
        <button
          onClick={() => navigate('/chat')}
          className={cn(
            'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left',
            location.pathname === '/chat'
              ? 'bg-indigo-600 text-white'
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
                ? 'bg-indigo-600 text-white'
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
          {MOCK_DOCS.map((doc) => (
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
