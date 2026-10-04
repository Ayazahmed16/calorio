import { useState } from 'react'
import { api } from './api'

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
    <div>
      <h3>Restaurant estimate</h3>
      <form onSubmit={estimate}>
        <input
          placeholder="e.g. chicken biryani, restaurant, large"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>{loading ? 'Estimating...' : 'Estimate'}</button>
      </form>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {result && (
        <div>
          <p>
            <strong>{result.name}: {result.low} - {result.high} kcal</strong> (typical {result.mid})
          </p>
          <p>{result.note}</p>
          <p>Estimate only. Real portions and oil vary.</p>
          {['low', 'mid', 'high'].map(key => (
            <label key={key} style={{ marginRight: 12 }}>
              <input
                type="radio"
                name="estimate-choice"
                checked={choice === key}
                onChange={() => setChoice(key)}
              />
              {key === 'mid' ? 'Typical' : key === 'low' ? 'Low' : 'High'} ({result[key]})
            </label>
          ))}
          <div>
            <button onClick={log}>Log {result[choice]} kcal</button>
            <button onClick={() => setResult(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}