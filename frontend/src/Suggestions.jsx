import { useState, useEffect } from 'react'
import { api } from './api'

export default function Suggestions({ token, mealType, refresh, onSaved }) {
  const [data, setData] = useState(null)
  const [goal, setGoal] = useState({ calories: '', protein: '' })
  const [error, setError] = useState('')

  async function loadSuggestions() {
    try {
      setData(await api('/suggestions/', token))
    } catch {
      setError('Could not load suggestions.')
    }
  }

  useEffect(() => {
    loadSuggestions()
  }, [refresh])

  useEffect(() => {
    api('/goal/', token).then(setGoal).catch(() => {})
  }, [])

  async function saveGoal(e) {
    e.preventDefault()
    setError('')
    try {
      await api('/goal/', token, {
        method: 'PUT',
        body: JSON.stringify({ calories: Number(goal.calories), protein: Number(goal.protein) }),
      })
      loadSuggestions()
    } catch {
      setError('Goal must be 500-10000 kcal and 0-500 g protein.')
    }
  }

  async function logMeal(s) {
    for (const it of s.items) {
      await api('/meals/', token, {
        method: 'POST',
        body: JSON.stringify({ food: it.food.id, servings: it.servings, meal_type: mealType }),
      })
    }
    onSaved()
  }

  return (
    <div>
      <h2>What's left today</h2>

      <form onSubmit={saveGoal}>
        <input type="number" placeholder="Daily calories" value={goal.calories}
          onChange={e => setGoal({ ...goal, calories: e.target.value })} required />
        <input type="number" placeholder="Daily protein (g)" value={goal.protein}
          onChange={e => setGoal({ ...goal, protein: e.target.value })} required />
        <button type="submit">Save goal</button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {data && (
        <div>
          <p>
            Left: {data.left.calories} kcal, {data.left.protein} g protein
          </p>

          {data.left.calories <= 0 && <p>You have reached your calorie goal for today.</p>}

          {data.left.calories > 0 && data.suggestions.length === 0 && (
            <p>No foods fit what is left. Try a custom meal.</p>
          )}

          <ul>
            {data.suggestions.map((s, i) => (
              <li key={i}>
                {s.items.map(it => `${it.food.name} x${it.servings}`).join(' + ')}
                {' = '}{s.calories} kcal, {s.protein} g protein
                <button onClick={() => logMeal(s)}>Log</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}