import { useState, useEffect } from 'react'
import { api } from './api'
import { Card, PrimaryButton } from './ui'

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
    <Card title="What's left today">
      <form onSubmit={saveGoal} className="mb-4">
        <input type="number" placeholder="Daily calories" value={goal.calories}
          onChange={e => setGoal({ ...goal, calories: e.target.value })} required />
        <input type="number" placeholder="Daily protein (g)" value={goal.protein}
          onChange={e => setGoal({ ...goal, protein: e.target.value })} required />
        <button type="submit">Save goal</button>
      </form>

      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mb-4">{error}</p>}

      {data && (
        <div>
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="bg-[#131315] border border-white/10 p-4">
              <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-1">Calories left</p>
              <p className="font-mono text-xl font-bold text-white">
                {data.left.calories}<span className="text-sm text-neutral-500 ml-1">kcal</span>
              </p>
            </div>
            <div className="bg-[#131315] border border-white/10 p-4">
              <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-1">Protein left</p>
              <p className="font-mono text-xl font-bold text-white">
                {data.left.protein}<span className="text-sm text-neutral-500 ml-1">g</span>
              </p>
            </div>
          </div>

          {data.left.calories <= 0 && (
            <p className="font-mono text-sm text-neutral-400">You have reached your calorie goal for today.</p>
          )}

          {data.left.calories > 0 && data.suggestions.length === 0 && (
            <p className="font-mono text-sm text-neutral-400">No foods fit what is left. Try a custom meal.</p>
          )}

          <ul>
            {data.suggestions.map((s, i) => (
              <li key={i} className="bg-[#131315] border border-white/10 p-4 font-mono text-sm text-white flex flex-wrap items-center justify-between gap-3">
                <span>
                  {s.items.map(it => `${it.food.name} x${it.servings}`).join(' + ')}
                  <span className="text-neutral-500"> = {s.calories} kcal, {s.protein} g protein</span>
                </span>
                <button onClick={() => logMeal(s)}>Log</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}