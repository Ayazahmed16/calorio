import { useState } from 'react'
import { api } from './api'
import { PrimaryButton } from './ui'

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
    <div className="mt-6 pt-6 border-t border-white/10">
      <h3 className="!mt-0">Quick log</h3>
      <form onSubmit={parse}>
        <input
          className="w-full md:w-96"
          placeholder="e.g. 2 rotis, dal and a samosa"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <PrimaryButton type="submit" disabled={loading}>{loading ? 'Reading...' : 'Parse'}</PrimaryButton>
      </form>
      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mt-2">{error}</p>}

      {preview && (
        <div className="bg-[#131315] border border-white/10 p-4 mt-3">
          <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-3">
            Check this before saving
          </p>
          <ul>
            {preview.items.map((it, i) => (
              <li key={i} className="font-mono text-sm text-white">
                {it.food.name} x{it.servings}
                <span className="text-neutral-500"> = {Math.round(it.food.calories * it.servings)} kcal</span>
              </li>
            ))}
            {preview.unmatched.map((u, i) => (
              <li key={i} className="font-mono text-sm text-white">
                {u.name}
                <span className="text-neutral-500"> ~{u.calories} kcal (estimate)</span>
              </li>
            ))}
          </ul>
          <button onClick={confirm}>Confirm</button>
          <button onClick={() => setPreview(null)}>Cancel</button>
        </div>
      )}
    </div>
  )
}