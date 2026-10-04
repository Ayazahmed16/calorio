import { useState, useEffect, useRef } from 'react'
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { api } from './api'
import { PrimaryButton } from './ui'

export default function BarcodeScan({ token, mealType, onSaved }) {
  const [manual, setManual] = useState('')
  const [scanning, setScanning] = useState(false)
  const [product, setProduct] = useState(null)
  const [grams, setGrams] = useState(100)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const handled = useRef(false)

  async function lookup(code) {
    setLoading(true)
    setError('')
    setProduct(null)
    try {
      const data = await api(`/barcode/${code}/`, token)
      setProduct(data)
      setGrams(data.serving_grams || 100)
    } catch {
      setError('Product not found or has no calorie data. Try another, or use Custom meal.')
    }
    setLoading(false)
  }

  useEffect(() => {
    if (!scanning) return
    handled.current = false

    const scanner = new Html5Qrcode('barcode-reader', {
      verbose: false,
      formatsToSupport: [
        Html5QrcodeSupportedFormats.EAN_13,
        Html5QrcodeSupportedFormats.EAN_8,
        Html5QrcodeSupportedFormats.UPC_A,
        Html5QrcodeSupportedFormats.UPC_E,
      ],
    })

    const started = scanner
      .start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 260, height: 140 } },
        code => {
          if (handled.current) return
          handled.current = true
          setScanning(false)
          lookup(code)
        },
        () => {}
      )
      .catch(() => {
        setError('Camera not available. Type the barcode below instead.')
        setScanning(false)
      })

    return () => {
      started
        .then(() => scanner.stop())
        .then(() => scanner.clear())
        .catch(() => {})
    }
  }, [scanning])

  function lookupManual(e) {
    e.preventDefault()
    lookup(manual.trim())
  }

  function scaled(value) {
    return Math.round(((value * grams) / 100) * 10) / 10
  }

  async function log() {
    await api('/meals/', token, {
      method: 'POST',
      body: JSON.stringify({
        name: `${product.name} (${grams} g)`,
        calories: Math.round((product.per100.calories * grams) / 100),
        protein: scaled(product.per100.protein),
        carbs: scaled(product.per100.carbs),
        fat: scaled(product.per100.fat),
        meal_type: mealType,
      }),
    })
    setProduct(null)
    setManual('')
    onSaved()
  }

  return (
    <div className="mt-6 pt-6 border-t border-white/10">
      <h3 className="!mt-0">Scan barcode</h3>

      {scanning ? (
        <div className="mb-4">
          <div id="barcode-reader" style={{ width: 300, margin: '0 auto' }} />
          <button onClick={() => setScanning(false)}>Stop camera</button>
        </div>
      ) : (
        <button onClick={() => { setError(''); setScanning(true) }}>Scan with camera</button>
      )}

      <form onSubmit={lookupManual} className="mt-2">
        <input
          placeholder="or type barcode digits"
          value={manual}
          onChange={e => setManual(e.target.value)}
          inputMode="numeric"
        />
        <PrimaryButton type="submit" disabled={loading}>{loading ? 'Looking...' : 'Look up'}</PrimaryButton>
      </form>

      {error && <p className="font-mono text-xs text-red-400 uppercase tracking-widest mt-2">{error}</p>}

      {product && (
        <div className="bg-[#131315] border border-white/10 p-4 mt-3">
          <p className="font-mono text-sm text-white mb-1">
            <strong>{product.name}</strong> {product.brand && `(${product.brand})`}
          </p>
          <p className="font-mono text-xs text-neutral-400 mb-1">
            Per 100 g: {product.per100.calories} kcal, P {product.per100.protein} /
            C {product.per100.carbs} / F {product.per100.fat}
          </p>
          {product.serving_size && (
            <p className="font-mono text-xs text-neutral-400 mb-3">Serving: {product.serving_size}</p>
          )}
          <label className="font-mono text-sm text-neutral-300">
            Grams eaten:{' '}
            <input
              type="number"
              min="1"
              max="5000"
              value={grams}
              onChange={e => setGrams(Number(e.target.value))}
            />
          </label>
          <p className="font-mono text-sm text-white mb-3">
            You ate: {Math.round((product.per100.calories * grams) / 100)} kcal
          </p>
          <button onClick={log} disabled={!grams || grams <= 0}>Log</button>
          <button onClick={() => setProduct(null)}>Cancel</button>
          <p className="font-mono text-[11px] text-neutral-600 mt-3">
            Data from Open Food Facts (ODbL license).
          </p>
        </div>
      )}
    </div>
  )
}