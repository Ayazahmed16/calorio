import { useState } from 'react'
import { api } from './api'

export default function Recipes({ token, mealType, onSaved }) {
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function find(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      setResult(
        await api('/recipes/', token, {
          method: 'POST',
          body: JSON.stringify({ ingredients: text }),
        })
      )
    } catch {
      setError('Could not make recipes. Try again.')
    }
    setLoading(false)
  }

  async function log(r) {
    await api('/meals/', token, {
      method: 'POST',
      body: JSON.stringify({
        name: r.name,
        calories: r.calories,
        protein: r.protein,
        carbs: r.carbs,
        fat: r.fat,
        meal_type: mealType,
      }),
    })
    onSaved()
  }

  return (
    <div>
      <h3>Cook from my fridge</h3>
      <form onSubmit={find}>
        <input
          placeholder="eggs, spinach, rice, paneer"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>{loading ? 'Thinking...' : 'Find recipes'}</button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {result && result.left.calories <= 0 && <p>You have reached your calorie goal for today.</p>}

      {result && result.left.calories > 0 && result.recipes.length === 0 && (
        <p>No recipe fit what is left. Try other ingredients.</p>
      )}

      {result && result.recipes.map((r, i) => (
        <div key={i}>
          <p>
            <strong>{r.name}</strong>: {r.calories} kcal, {r.protein} g protein
            {r.minutes > 0 && ` (${r.minutes} min)`}
          </p>
          <p>Uses: {r.ingredients_used.join(', ') || '-'}</p>
          {r.extra_needed.length > 0 && <p>Also need: {r.extra_needed.join(', ')}</p>}
          <details>
            <summary>Steps</summary>
            <ol>
              {r.steps.map((s, j) => <li key={j}>{s}</li>)}
            </ol>
          </details>
          <button onClick={() => log(r)}>Log 1 serving</button>
        </div>
      ))}

      {result && result.recipes.length > 0 && <p>Calories are estimates.</p>}
    </div>
  )
}