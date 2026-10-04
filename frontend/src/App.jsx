import { useState, useEffect } from 'react'
import { login, api } from './api'
import QuickLog from './QuickLog'
import RestaurantEstimate from './RestaurantEstimate'
import BarcodeScan from './BarcodeScan'
import Suggestions from './Suggestions'
import Recipes from './Recipe'
import Streaks from './Streaks'
import Challenges from './Challenges'
import Report from './Report'
import { PageShell, PageHeader, Card, PrimaryButton, GhostButton } from './ui'

const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack']

function sum(list, key) {
  return Math.round(list.reduce((t, m) => t + m[key], 0) * 10) / 10
}

function Stat({ label, value, unit }) {
  return (
    <div className="bg-[#1c1b1d] border border-white/10 p-5">
      <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-2">{label}</p>
      <p className="font-mono text-2xl font-bold text-white tracking-tighter">
        {value}
        {unit && <span className="text-sm text-neutral-500 ml-1">{unit}</span>}
      </p>
    </div>
  )
}

function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      const token = await login(username, password)
      onLogin(token)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <PageShell>
      <div className="flex items-center justify-center min-h-[80vh]">
        <form onSubmit={handleSubmit} className="w-full max-w-md bg-[#1c1b1d] border border-white/10 p-8">
          <span className="font-mono text-[11px] text-neutral-400 uppercase tracking-[0.3em] block mb-3">
            Authentication / Awaiting Input
          </span>
          <h1 className="text-3xl font-bold text-white tracking-tighter uppercase mb-6">Calorio</h1>
          {error && (
            <p className="font-mono text-xs text-red-400 uppercase tracking-widest mb-4">{error}</p>
          )}
          <input
            className="w-full"
            placeholder="Username"
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
          <input
            className="w-full"
            placeholder="Password"
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
          <div className="mt-4">
            <PrimaryButton type="submit">Login</PrimaryButton>
          </div>
        </form>
      </div>
    </PageShell>
  )
}

function Dashboard({ token, onLogout }) {
  const today = new Date().toLocaleDateString('en-CA')

  const [summary, setSummary] = useState(null)
  const [meals, setMeals] = useState([])
  const [activities, setActivities] = useState([])

  // food search
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [servings, setServings] = useState(1)
  const [mealType, setMealType] = useState('breakfast')

  // custom meal
  const [name, setName] = useState('')
  const [calories, setCalories] = useState('')
  const [protein, setProtein] = useState('')

  // steps
  const [steps, setSteps] = useState('')
  const [date, setDate] = useState(today)

  async function load() {
    setSummary(await api('/summary/', token))
    setMeals(await api('/meals/', token))
    setActivities(await api('/activities/', token))
  }

  useEffect(() => {
    load()
  }, [])

  // search runs 300 ms after you stop typing
  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    const timer = setTimeout(async () => {
      setResults(await api(`/foods/?search=${encodeURIComponent(query)}`, token))
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  async function addFood(e) {
    e.preventDefault()
    await api('/meals/', token, {
      method: 'POST',
      body: JSON.stringify({ food: selected.id, servings: Number(servings), meal_type: mealType }),
    })
    setSelected(null)
    setQuery('')
    setResults([])
    setServings(1)
    load()
  }

  async function addCustom(e) {
    e.preventDefault()
    await api('/meals/', token, {
      method: 'POST',
      body: JSON.stringify({
        name,
        calories: Number(calories),
        protein: Number(protein) || 0,
        meal_type: mealType,
      }),
    })
    setName('')
    setCalories('')
    setProtein('')
    load()
  }

  async function deleteMeal(id) {
    await api(`/meals/${id}/`, token, { method: 'DELETE' })
    load()
  }

  async function addActivity(e) {
    e.preventDefault()
    await api('/activities/', token, {
      method: 'POST',
      body: JSON.stringify({ date, steps: Number(steps) }),
    })
    setSteps('')
    load()
  }

  async function deleteActivity(id) {
    await api(`/activities/${id}/`, token, { method: 'DELETE' })
    load()
  }

  if (!summary) {
    return (
      <PageShell>
        <p className="font-mono text-sm text-neutral-500 uppercase tracking-widest">Loading...</p>
      </PageShell>
    )
  }

  const todayMeals = meals.filter(m => m.eaten_at.slice(0, 10) === today)

  return (
    <PageShell>
      <div className="max-w-5xl mx-auto">
        <PageHeader
          kicker={`Daily Tracking / ${today}`}
          title="Calorio"
          right={<GhostButton onClick={onLogout}>Logout</GhostButton>}
        />

        <h2>Today</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10">
          <Stat label="Calories" value={summary.today.calories} unit="kcal" />
          <Stat label="Protein" value={summary.today.protein} unit="g" />
          <Stat label="Carbs" value={sum(todayMeals, 'carbs')} unit="g" />
          <Stat label="Fat" value={sum(todayMeals, 'fat')} unit="g" />
          <Stat label="Steps" value={summary.today.steps} />
        </div>

        <section className="mb-10">
          <Suggestions token={token} mealType={mealType} refresh={meals.length} onSaved={load} />
        </section>
        <Streaks token={token} refresh={meals.length + activities.length} />
        <section className="mb-10">
          <Challenges token={token} refresh={meals.length + activities.length} />
        </section>
        <section className="mb-10">
          <Report token={token} />
        </section>

        <h2>Add food</h2>
        <Card className="mb-10">
          <select value={mealType} onChange={e => setMealType(e.target.value)}>
            {MEAL_TYPES.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <QuickLog token={token} mealType={mealType} onSaved={load} />
          <RestaurantEstimate token={token} mealType={mealType} onSaved={load} />
          <BarcodeScan token={token} mealType={mealType} onSaved={load} />
          <Recipes token={token} mealType={mealType} onSaved={load} />

          <h3>Search food</h3>
          {selected ? (
            <form onSubmit={addFood}>
              <p className="font-mono text-sm text-white mb-3">
                {selected.name} ({selected.serving_unit}): {selected.calories} kcal per serving
              </p>
              <input
                type="number"
                min="0.5"
                step="0.5"
                value={servings}
                onChange={e => setServings(e.target.value)}
                required
              />
              <button type="submit">Add</button>
              <button type="button" onClick={() => setSelected(null)}>Cancel</button>
            </form>
          ) : (
            <div>
              <input
                className="w-full"
                placeholder="Search food (roti, dal, biryani...)"
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
              <ul>
                {results.map(f => (
                  <li key={f.id} className="font-mono text-sm text-white">
                    {f.name} ({f.serving_unit}) - {f.calories} kcal
                    <button className="ml-3" onClick={() => setSelected(f)}>Select</button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <h3>Custom meal</h3>
          <form onSubmit={addCustom}>
            <input placeholder="Name" value={name} onChange={e => setName(e.target.value)} required />
            <input placeholder="Calories" type="number" value={calories} onChange={e => setCalories(e.target.value)} required />
            <input placeholder="Protein" type="number" value={protein} onChange={e => setProtein(e.target.value)} />
            <button type="submit">Add</button>
          </form>
        </Card>

        <h2>Today's diary</h2>
        <div className="grid md:grid-cols-2 gap-4 mb-10">
          {MEAL_TYPES.map(type => {
            const items = todayMeals.filter(m => m.meal_type === type)
            return (
              <Card key={type} title={`${type} - ${sum(items, 'calories')} kcal`}>
                <ul>
                  {items.map(m => (
                    <li key={m.id} className="font-mono text-sm text-white">
                      {m.name} x{m.servings} - {m.calories} kcal
                      <span className="text-neutral-500"> (P {m.protein} / C {m.carbs} / F {m.fat})</span>
                      <button className="ml-3" onClick={() => deleteMeal(m.id)}>Delete</button>
                    </li>
                  ))}
                  {items.length === 0 && (
                    <li className="font-mono text-xs text-neutral-600 uppercase tracking-widest">Nothing logged</li>
                  )}
                </ul>
              </Card>
            )
          })}
        </div>

        <h2>Add steps</h2>
        <Card className="mb-10">
          <form onSubmit={addActivity}>
            <input type="date" value={date} onChange={e => setDate(e.target.value)} required />
            <input placeholder="Steps" type="number" value={steps} onChange={e => setSteps(e.target.value)} required />
            <button type="submit">Add</button>
          </form>
        </Card>

        <div className="grid md:grid-cols-2 gap-4 pb-16">
          <Card title="Activity">
            <ul>
              {activities.map(a => (
                <li key={a.id} className="font-mono text-sm text-white">
                  {a.date}: {a.steps} steps
                  <button className="ml-3" onClick={() => deleteActivity(a.id)}>Delete</button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Daily history">
            <ul>
              {summary.daily.map(d => (
                <li key={d.day} className="font-mono text-sm text-white">
                  {d.day}: {d.calories} kcal, {d.protein} g
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </PageShell>
  )
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))

  function handleLogin(t) {
    localStorage.setItem('token', t)
    setToken(t)
  }

  function handleLogout() {
    localStorage.removeItem('token')
    setToken(null)
  }

  if (!token) return <Login onLogin={handleLogin} />
  return <Dashboard token={token} onLogout={handleLogout} />
}