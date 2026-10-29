import { ImageResponse } from 'next/og'

export const alt = 'NEXORA Gateway: one governed entry point for every model call'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

// Social preview card. Colors mirror app/tokens.css (dark theme): background #0c0f14, accent #4fd1c1, text #eef1f5.
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: 80, background: '#0c0f14', color: '#eef1f5', fontFamily: 'sans-serif' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <svg width="96" height="96" viewBox="0 0 64 64">
            <rect width="64" height="64" rx="14" fill="#0b6b63" />
            <path d="M20 50V24a12 12 0 0 1 24 0v26" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
            <rect x="29" y="32" width="6" height="18" rx="3" fill="#fff" />
          </svg>
          <div style={{ display: 'flex', fontSize: 44, fontWeight: 700, letterSpacing: 2, color: '#4fd1c1' }}>NEXORA Gateway</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', fontSize: 76, fontWeight: 700, lineHeight: 1.08 }}>One governed entry point for every model call.</div>
          <div style={{ display: 'flex', fontSize: 34, color: '#a9b4c2' }}>One key. Rate limits, quotas, policies and an audit log.</div>
        </div>
        <div style={{ display: 'flex', fontSize: 28, color: '#4fd1c1' }}>gateway.onenexora.com</div>
      </div>
    ),
    size,
  )
}
