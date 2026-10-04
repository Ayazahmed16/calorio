import { useState, useEffect } from 'react'
import { api, BASE } from './api'

export default function Report({ token }) {
  const [email, setEmail] = useState('')
  const [weekly, setWeekly] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api('/report/settings/', token)
      .then(s => {
        setEmail(s.email)
        setWeekly(s.weekly_email)
      })
      .catch(() => {})
  }, [])

  async function save(e) {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      await api('/report/settings/', token, {
        method: 'PUT',
        body: JSON.stringify({ email, weekly_email: weekly }),
      })
      setMessage('Saved.')
    } catch {
      setError('Enter a valid email to turn on weekly reports.')
    }
  }

  async function download() {
    setError('')
    setMessage('')
    try {
      const res = await fetch(`${BASE}/report/weekly/`, {
        headers: { Authorization: `Token ${token}` },
      })
      if (!res.ok) throw new Error()
      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'calorio-weekly-report.pdf'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      setError('Could not make the report. Try again.')
    }
  }

  return (
    <div>
      <h2>Weekly report</h2>
      <button onClick={download}>Download this week's PDF</button>

      <form onSubmit={save}>
        <input
          type="email"
          placeholder="Your email"
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
        <label>
          <input type="checkbox" checked={weekly} onChange={e => setWeekly(e.target.checked)} />
          Email me the report every Sunday
        </label>
        <button type="submit">Save</button>
      </form>

      {message && <p>{message}</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  )
}