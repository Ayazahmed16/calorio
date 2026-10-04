import { useState, useEffect } from 'react'
import { api, BASE } from './api'
import { Card, PrimaryButton } from './ui'

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
    <Card title="Weekly report">
      <div className="mb-6">
        <PrimaryButton onClick={download}>Download this week's PDF</PrimaryButton>
      </div>

      <form onSubmit={save}>
        <input
          type="email"
          placeholder="Your email"
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
        <label className="font-mono text-sm text-neutral-300 block my-3">
          <input
            type="checkbox"
            checked={weekly}
            onChange={e => setWeekly(e.target.checked)}
            style={{ padding: 0, margin: '0 0.6rem 0 0' }}
          />
          Email me the report every Sunday
        </label>
        <button type="submit">Save</button>
      </form>

      {message && <p className="font-mono text-xs text-[#22c55e] uppercase tracking-widest mt-3">{message}</p>}
      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mt-3">{error}</p>}
    </Card>
  )
}