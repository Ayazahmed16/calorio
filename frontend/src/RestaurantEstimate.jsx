import { useState } from 'react'
import { api } from './api'
import { PrimaryButton } from './ui'

export default function RestaurantEstimate({ token, mealType, onSaved }) {
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [choice, setChoice] = useState('mid')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function estimate(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const data = await api('/estimate-meal/', token, {
        method: 'POST',
        body: JSON.stringify({ text }),
      })
      setResult(data)
      setChoice('mid')
    } catch {
      setError('Could not estimate that. Try again.')
    }
    setLoading(false)
  }

  async function log() {
    // macros are for the typical case, so scale them to the chosen value
    const factor = result.mid ? result[choice] / result.mid : 1
    const round1 = n => Math.round(n * 10) / 10
    await api('/meals/', token, {
      method: 'POST',
      body: JSON.stringify({
        name: `${result.name} (restaurant)`,
        calories: result[choice],
        protein: round1(result.protein * factor),
        carbs: round1(result.carbs * factor),
        fat: round1(result.fat * factor),
        meal_type: mealType,
      }),
    })
    setResult(null)
    setText('')
    onSaved()
  }

  return (
    <div className="mt-6 pt-6 border-t border-white/10">
      <h3 className="!mt-0">Restaurant estimate</h3>
      <form onSubmit={estimate}>
        <input
          className="w-full md:w-96"
          placeholder="e.g. chicken biryani, restaurant, large"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <PrimaryButton type="submit" disabled={loading}>{loading ? 'Estimating...' : 'Estimate'}</PrimaryButton>
      </form>
      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mt-2">{error}</p>}

      {result && (
        <div className="bg-[#131315] border border-white/10 p-4 mt-3">
          <p className="font-mono text-sm text-white mb-1">
            <strong>{result.name}: {result.low} - {result.high} kcal</strong>
            <span className="text-neutral-500"> (typical {result.mid})</span>
          </p>
          <p className="font-mono text-xs text-neutral-400 mb-1">{result.note}</p>
          <p className="font-mono text-[11px] text-neutral-600 uppercase tracking-widest mb-4">
            Estimate only. Real portions and oil vary.
          </p>
          {['low', 'mid', 'high'].map(key => (
            <label key={key} className="font-mono text-sm text-neutral-300 mr-5">
              <input
                type="radio"
                name="estimate-choice"
                checked={choice === key}
                onChange={() => setChoice(key)}
                style={{ padding: 0, margin: '0 0.4rem 0 0' }}
              />
              {key === 'mid' ? 'Typical' : key === 'low' ? 'Low' : 'High'} ({result[key]})
            </label>
          ))}
          <div className="mt-4">
            <button onClick={log}>Log {result[choice]} kcal</button>
            <button onClick={() => setResult(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}