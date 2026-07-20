import { useEffect, useState } from 'react'
import { API_URL } from '@/lib/api'

interface Branding {
  appName: string
  theme: string
}

export function useBranding(): Branding {
  const [branding, setBranding] = useState<Branding>({ appName: 'DocBot', theme: 'indigo' })

  useEffect(() => {
    fetch(`${API_URL}/branding`)
      .then((r) => r.json())
      .then((d) => setBranding({ appName: d.app_name, theme: d.theme }))
      .catch(() => {})
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', branding.theme)
  }, [branding.theme])

  return branding
}
