import { useState, useEffect } from 'react'
import { api, BASE } from './api'

const METRIC_LABEL = { steps: 'Steps', protein: 'Protein (g)', logging: 'Days logged' }
// http://127.0.0.1:8000/api  ->  ws://127.0.0.1:8000   (https becomes wss)
const WS_BASE = BASE.replace(/^http/, 'ws').replace(/\/api$/, '')

export default function Challenges({ token, refresh }) {
  const today = new Date().toLocaleDateString('en-CA')
  const weekLater = new Date(Date.now() + 6 * 86400000).toLocaleDateString('en-CA')

  const [list, setList] = useState([])
  const [detail, setDetail] = useState(null)
  const [live, setLive] = useState(false)
  const [error, setError] = useState('')
  const [code, setCode] = useState('')
  const [form, setForm] = useState({
    name: '',
    metric: 'steps',
    start_date: today,
    end_date: weekLater,
  })

  async function loadList() {
    setList(await api('/challenges/', token))
  }

  async function open(id) {
    try {
      setDetail(await api(`/challenges/${id}/`, token))
    } catch {
      setError('Could not open that challenge.')
    }
  }

  useEffect(() => {
    loadList().catch(() => {})
  }, [])

  // refresh the open leaderboard when you log meals or steps yourself
  useEffect(() => {
    if (detail) open(detail.id)
  }, [refresh])

  // live updates: one WebSocket for the challenge that is open
  const openId = detail ? detail.id : null
  useEffect(() => {
    if (!openId) return
    const ws = new WebSocket(`${WS_BASE}/ws/challenges/${openId}/`)

    ws.onopen = () => ws.send(JSON.stringify({ token }))
    ws.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'ready') setLive(true)
      if (msg.type === 'refresh') {
        api(`/challenges/${openId}/`, token).then(setDetail).catch(() => {})
      }
    }
    ws.onclose = () => setLive(false)

    return () => ws.close()
  }, [openId])

  async function create(e) {
    e.preventDefault()
    setError('')
    try {
      const c = await api('/challenges/', token, {
        method: 'POST',
        body: JSON.stringify(form),
      })
      setForm({ ...form, name: '' })
      await loadList()
      open(c.id)
    } catch {
      setError('Could not create it. Check the name and dates (max 90 days).')
    }
  }

  async function join(e) {
    e.preventDefault()
    setError('')
    try {
      const c = await api('/challenges/join/', token, {
        method: 'POST',
        body: JSON.stringify({ code }),
      })
      setCode('')
      await loadList()
      open(c.id)
    } catch {
      setError('Invalid invite code, or the challenge has ended or is full.')
    }
  }

  async function leave() {
    await api(`/challenges/${detail.id}/leave/`, token, { method: 'POST' })
    setDetail(null)
    loadList()
  }

  return (
    <div>
      <h2>Challenges</h2>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <h3>My challenges</h3>
      <ul>
        {list.map(c => (
          <li key={c.id}>
            {c.name} - {METRIC_LABEL[c.metric]} ({c.status}, {c.members} members)
            <button onClick={() => open(c.id)}>Open</button>
          </li>
        ))}
        {list.length === 0 && <li>No challenges yet.</li>}
      </ul>

      {detail && (
        <div>
          <h3>{detail.name} {live && <small>● Live</small>}</h3>
          <p>
            {METRIC_LABEL[detail.metric]}, {detail.start_date} to {detail.end_date} ({detail.status})
          </p>
          <p>Invite code: <strong>{detail.invite_code}</strong></p>
          <ol style={{ listStyle: 'none', padding: 0 }}>
            {detail.leaderboard.map(r => (
              <li key={r.id} style={{ fontWeight: r.username === detail.me ? 'bold' : 'normal' }}>
                #{r.rank} {r.username}{r.username === detail.me ? ' (you)' : ''}: {r.score}
              </li>
            ))}
          </ol>
          <button onClick={leave}>Leave challenge</button>
          <button onClick={() => setDetail(null)}>Close</button>
        </div>
      )}

      <h3>Create a challenge</h3>
      <form onSubmit={create}>
        <input
          placeholder="Name"
          maxLength={60}
          value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })}
          required
        />
        <select value={form.metric} onChange={e => setForm({ ...form, metric: e.target.value })}>
          {Object.entries(METRIC_LABEL).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <input type="date" value={form.start_date}
          onChange={e => setForm({ ...form, start_date: e.target.value })} required />
        <input type="date" value={form.end_date}
          onChange={e => setForm({ ...form, end_date: e.target.value })} required />
        <button type="submit">Create</button>
      </form>

      <h3>Join with a code</h3>
      <form onSubmit={join}>
        <input placeholder="Invite code" value={code} onChange={e => setCode(e.target.value)} required />
        <button type="submit">Join</button>
      </form>
    </div>
  )
}