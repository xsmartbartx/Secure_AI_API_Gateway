import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: { default: 'NEXORA Gateway', template: '%s · NEXORA Gateway' },
  description: 'One governed entry point for every model call your organization makes.',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>
}
