import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { API_URL } from '@/lib/api'

const WAVES = [
  { color: [99,  102, 241], alpha: 0.45, speed: 0.4,  amplitude: 90,  frequency: 0.007, yRatio: 0.55 },
  { color: [139,  92, 246], alpha: 0.35, speed: 0.65, amplitude: 70,  frequency: 0.010, yRatio: 0.62 },
  { color: [59,  130, 246], alpha: 0.28, speed: 0.25, amplitude: 110, frequency: 0.005, yRatio: 0.48 },
  { color: [168,  85, 247], alpha: 0.22, speed: 0.85, amplitude: 55,  frequency: 0.013, yRatio: 0.70 },
  { color: [79,  70,  229], alpha: 0.18, speed: 0.55, amplitude: 80,  frequency: 0.009, yRatio: 0.40 },
]

function WaveCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    let t = 0

    function resize() {
      canvas!.width  = window.innerWidth
      canvas!.height = window.innerHeight
    }

    function draw() {
      const { width, height } = canvas!
      ctx!.clearRect(0, 0, width, height)

      for (const w of WAVES) {
        ctx!.beginPath()
        ctx!.moveTo(0, height)

        for (let x = 0; x <= width; x += 2) {
          const y =
            height * w.yRatio +
            Math.sin(x * w.frequency + t * w.speed) * w.amplitude +
            Math.sin(x * w.frequency * 1.8 + t * w.speed * 1.4) * (w.amplitude * 0.4)
          ctx!.lineTo(x, y)
        }

        ctx!.lineTo(width, height)
        ctx!.lineTo(0, height)
        ctx!.closePath()
        ctx!.fillStyle = `rgba(${w.color[0]}, ${w.color[1]}, ${w.color[2]}, ${w.alpha})`
        ctx!.fill()
      }

      t += 0.018
      animId = requestAnimationFrame(draw)
    }

    resize()
    window.addEventListener('resize', resize)
    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
}

export default function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const params = new URLSearchParams()
      params.append('username', username)
      params.append('password', password)

      const { data } = await axios.post(`${API_URL}/auth/login`, params)
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('role', data.role)
      navigate('/chat')
    } catch {
      setError('Invalid username or password.')
    }

    setLoading(false)
  }

  return (
    <div className="relative min-h-screen bg-[#05050a] overflow-hidden flex items-center justify-center p-4">

      {/* Animated wave canvas */}
      <WaveCanvas />

      {/* Subtle grid overlay */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      {/* Card */}
      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-indigo-600 mb-5 shadow-lg shadow-indigo-500/30">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">DocBot</h1>
          <p className="text-sm text-gray-400 mt-1">Knowledge base assistant</p>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-black/40 backdrop-blur-2xl p-8 shadow-2xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin or user"
                required
                className="w-full h-10 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full h-10 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
              />
            </div>

            {error && (
              <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-10 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors shadow-lg shadow-indigo-500/20 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-white/[0.06]">
            <p className="text-xs text-gray-600 mb-2">Demo credentials</p>
            <div className="space-y-1">
              <p className="text-xs text-gray-500 font-mono">user / user123</p>
              <p className="text-xs text-gray-500 font-mono">admin / admin123</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
