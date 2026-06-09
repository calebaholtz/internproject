import { Navigate } from 'react-router-dom'

interface Props {
  children: React.ReactNode
  requireAdmin?: boolean
}

export default function ProtectedRoute({ children, requireAdmin = false }: Props) {
  const token = localStorage.getItem('token')
  const role = localStorage.getItem('role')

  if (!token) return <Navigate to="/login" replace />
  if (requireAdmin && role !== 'admin') return <Navigate to="/chat" replace />

  return <>{children}</>
}
