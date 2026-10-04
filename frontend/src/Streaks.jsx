import { useState, useEffect } from 'react'
import { api } from './api'

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
    <div>
      <h2>Streaks</h2>
      <Streak label="Logging" data={data.streaks.logging} />
      <Streak label="Protein goal" data={data.streaks.protein} />
      <Streak label="8000 steps" data={data.streaks.steps} />

      <h3>Badges</h3>
      <ul>
        {data.badges.map(b => (
          <li key={b.code} style={{ opacity: b.earned ? 1 : 0.4 }}>
            {b.earned ? '🏅' : '🔒'} <strong>{b.name}</strong> - {b.description}
          </li>
        ))}
      </ul>
    </div>
  )
}