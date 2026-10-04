import { useState, useEffect } from 'react'
import { api } from './api'
import { PageShell, PageHeader, Card } from './ui'
function Streak({ label, data }) {
  return (
    <p>
      {label}: {data.current} day{data.current === 1 ? '' : 's'} (best {data.best})
    </p>
  )
}

export default function Streaks({ token, refresh }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    api('/streaks/', token).then(setData).catch(() => {})
  }, [refresh])

  if (!data) return null

return (
  <PageShell>
    <PageHeader kicker="Daily Tracking / Active" title="Streaks" />

    <div className="grid md:grid-cols-3 gap-4 mb-12">
      <Streak label="Logging" data={data.streaks.logging} />
      <Streak label="Protein goal" data={data.streaks.protein} />
      <Streak label="8000 steps" data={data.streaks.steps} />
    </div>

    <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-4">Badges</p>
    <ul className="grid md:grid-cols-2 gap-3">
      {data.badges.map(b => (
        <li
          key={b.code}
          className="bg-[#1c1b1d] border border-white/10 p-4 font-mono text-sm text-white"
          style={{ opacity: b.earned ? 1 : 0.4 }}
        >
          {b.earned ? '🏅' : '🔒'} <strong>{b.name}</strong> - {b.desc}
        </li>
      ))}
    </ul>
  </PageShell>
)
}