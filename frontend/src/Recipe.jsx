import { useState } from 'react'
import { api } from './api'
import { PrimaryButton } from './ui'

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
    <div className="mt-6 pt-6 border-t border-white/10">
      <h3 className="!mt-0">Cook from my fridge</h3>
      <form onSubmit={find}>
        <input
          className="w-full md:w-96"
          placeholder="eggs, spinach, rice, paneer"
          value={text}
          onChange={e => setText(e.target.value)}
          required
        />
        <PrimaryButton type="submit" disabled={loading}>{loading ? 'Thinking...' : 'Find recipes'}</PrimaryButton>
      </form>

      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mt-2">{error}</p>}

      {result && result.left.calories <= 0 && (
        <p className="font-mono text-sm text-neutral-400 mt-3">You have reached your calorie goal for today.</p>
      )}

      {result && result.left.calories > 0 && result.recipes.length === 0 && (
        <p className="font-mono text-sm text-neutral-400 mt-3">No recipe fit what is left. Try other ingredients.</p>
      )}

      {result && result.recipes.map((r, i) => (
        <div key={i} className="bg-[#131315] border border-white/10 p-4 mt-3">
          <p className="font-mono text-sm text-white mb-1">
            <strong>{r.name}</strong>
            <span className="text-neutral-500">
              : {r.calories} kcal, {r.protein} g protein
              {r.minutes > 0 && ` (${r.minutes} min)`}
            </span>
          </p>
          <p className="font-mono text-xs text-neutral-400 mb-1">Uses: {r.ingredients_used.join(', ') || '-'}</p>
          {r.extra_needed.length > 0 && (
            <p className="font-mono text-xs text-neutral-400 mb-1">Also need: {r.extra_needed.join(', ')}</p>
          )}
          <details className="font-mono text-sm text-neutral-300 my-3">
            <summary className="cursor-pointer text-neutral-400 uppercase text-[11px] tracking-widest">Steps</summary>
            <ol className="list-decimal ml-5 mt-2">
              {r.steps.map((s, j) => <li key={j}>{s}</li>)}
            </ol>
          </details>
          <button onClick={() => log(r)}>Log 1 serving</button>
        </div>
      ))}

      {result && result.recipes.length > 0 && (
        <p className="font-mono text-[11px] text-neutral-600 uppercase tracking-widest mt-3">Calories are estimates.</p>
      )}
    </div>
  )
}