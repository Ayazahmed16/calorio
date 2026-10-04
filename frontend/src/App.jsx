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
const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack']

function sum(list, key) {
  return Math.round(list.reduce((t, m) => t + m[key], 0) * 10) / 10
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
    <form onSubmit={handleSubmit}>
      <h1>Calorio Login</h1>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <input placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} />
      <input placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} />
      <button type="submit">Login</button>
    </form>
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

  if (!summary) return <p>Loading...</p>

  const todayMeals = meals.filter(m => m.eaten_at.slice(0, 10) === today)

  return (
    <div>
      <h1>Calorio</h1>
      <button onClick={onLogout}>Logout</button>

      <h2>Today</h2>
      <p>Calories: {summary.today.calories}</p>
      <p>Protein: {summary.today.protein} g</p>
      <p>Carbs: {sum(todayMeals, 'carbs')} g</p>
      <p>Fat: {sum(todayMeals, 'fat')} g</p>
      <p>Steps: {summary.today.steps}</p>
      <Suggestions token={token} mealType={mealType} refresh={meals.length} onSaved={load} />
      <Streaks token={token} refresh={meals.length + activities.length} />
      <Challenges token={token} refresh={meals.length + activities.length} />
      <Report token={token} />
      <h2>Add food</h2>
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
          <p>
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
          <input placeholder="Search food (roti, dal, biryani...)" value={query} onChange={e => setQuery(e.target.value)} />
          <ul>
            {results.map(f => (
              <li key={f.id}>
                {f.name} ({f.serving_unit}) - {f.calories} kcal
                <button onClick={() => setSelected(f)}>Select</button>
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

      <h2>Today's diary</h2>
      {MEAL_TYPES.map(type => {
        const items = todayMeals.filter(m => m.meal_type === type)
        return (
          <div key={type}>
            <h3 style={{ textTransform: 'capitalize' }}>
              {type} - {sum(items, 'calories')} kcal
            </h3>
            <ul>
              {items.map(m => (
                <li key={m.id}>
                  {m.name} x{m.servings} - {m.calories} kcal (P {m.protein} / C {m.carbs} / F {m.fat})
                  <button onClick={() => deleteMeal(m.id)}>Delete</button>
                </li>
              ))}
            </ul>
          </div>
        )
      })}

      <h2>Add steps</h2>
      <form onSubmit={addActivity}>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} required />
        <input placeholder="Steps" type="number" value={steps} onChange={e => setSteps(e.target.value)} required />
        <button type="submit">Add</button>
      </form>

      <h2>Activity</h2>
      <ul>
        {activities.map(a => (
          <li key={a.id}>
            {a.date}: {a.steps} steps
            <button onClick={() => deleteActivity(a.id)}>Delete</button>
          </li>
        ))}
      </ul>

      <h2>Daily history</h2>
      <ul>
        {summary.daily.map(d => (
          <li key={d.day}>{d.day}: {d.calories} kcal, {d.protein} g</li>
        ))}
      </ul>
    </div>
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