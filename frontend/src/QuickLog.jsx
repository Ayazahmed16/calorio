import { useState } from 'react'
import { api } from './api'

export default function QuickLog({ token, mealType, onSaved }) {
  const [text, setText] = useState('')
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function parse(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api('/parse-meal/', token, {
        method: 'POST',
        body: JSON.stringify({ text }),
      })
      if (data.items.length === 0 && data.unmatched.length === 0) {
        setError('No food found. Try again.')
      } else {
        setPreview(data)
      }
    } catch {
      setError('Could not understand that. Try again.')
    }
    setLoading(false)
  }

  async function confirm() {
    for (const it of preview.items) {
      await api('/meals/', token, {
        method: 'POST',
        body: JSON.stringify({ food: it.food.id, servings: it.servings, meal_type: mealType }),
      })
    }
    for (const u of preview.unmatched) {
      await api('/meals/', token, {
        method: 'POST',
        body: JSON.stringify({
          name: u.name,
          calories: u.calories,
          protein: u.protein,
          carbs: u.carbs,
          fat: u.fat,
          meal_type: mealType,
        }),
      })
    }
    setPreview(null)
    setText('')
    onSaved()
  }

  return (
    <div>
      <h3>Quick log</h3>
      <form onSubmit={parse}>
        <input
          placeholder="e.g. 2 rotis, dal and a samosa"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>{loading ? 'Reading...' : 'Parse'}</button>
      </form>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {preview && (
        <div>
          <p>Check this before saving:</p>
          <ul>
            {preview.items.map((it, i) => (
              <li key={i}>
                {it.food.name} x{it.servings} = {Math.round(it.food.calories * it.servings)} kcal
              </li>
            ))}
            {preview.unmatched.map((u, i) => (
              <li key={i}>{u.name} ~{u.calories} kcal (estimate)</li>
            ))}
          </ul>
          <button onClick={confirm}>Confirm</button>
          <button onClick={() => setPreview(null)}>Cancel</button>
        </div>
      )}
    </div>
  )
}