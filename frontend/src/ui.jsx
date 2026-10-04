const HEX = '50,5 93,27.5 93,72.5 50,95 7,72.5 7,27.5'

const SHAPES = [
  { t: 'hex',  top: '4%',  left: '6%',  size: 90,  rot: 10,  dur: 22, delay: 0,  dx: 16, dy: -26 },
  { t: 'zig',  top: '10%', left: '28%', size: 70,  rot: -8,  dur: 18, delay: 2,  dx: -12, dy: 22 },
  { t: 'bond', top: '6%',  left: '52%', size: 110, rot: 20,  dur: 26, delay: 1,  dx: 18, dy: 20 },
  { t: 'hex',  top: '14%', left: '78%', size: 60,  rot: -15, dur: 20, delay: 4,  dx: -14, dy: -24 },
  { t: 'zig',  top: '36%', left: '90%', size: 80,  rot: 25,  dur: 24, delay: 3,  dx: -16, dy: 18 },
  { t: 'hex',  top: '42%', left: '4%',  size: 70,  rot: 5,   dur: 19, delay: 5,  dx: 14, dy: -20 },
  { t: 'bond', top: '52%', left: '22%', size: 100, rot: -20, dur: 28, delay: 2,  dx: 20, dy: 16 },
  { t: 'zig',  top: '58%', left: '60%', size: 90,  rot: 12,  dur: 21, delay: 6,  dx: -18, dy: -22 },
  { t: 'hex',  top: '66%', left: '84%', size: 100, rot: -10, dur: 25, delay: 1,  dx: 12, dy: 24 },
  { t: 'hex',  top: '80%', left: '10%', size: 80,  rot: 18,  dur: 23, delay: 3,  dx: 16, dy: -18 },
  { t: 'zig',  top: '84%', left: '38%', size: 70,  rot: -6,  dur: 17, delay: 7,  dx: -14, dy: 20 },
  { t: 'bond', top: '86%', left: '70%', size: 90,  rot: 8,   dur: 27, delay: 4,  dx: 18, dy: -22 },
]

function ShapePath({ t }) {
  if (t === 'hex') return <polygon points={HEX} />
  if (t === 'zig') return <polyline points="10,12 45,32 22,52 62,72 40,92" />
  return (
    <g>
      <polygon points={HEX} />
      <line x1="93" y1="27.5" x2="100" y2="12" />
    </g>
  )
}

export const FloatingShapes = () => (
  <div className="fixed inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
    {SHAPES.map((s, i) => (
      <svg
        key={i}
        className="float-shape"
        viewBox="0 0 100 100"
        width={s.size}
        height={s.size}
        fill="none"
        stroke="white"
        strokeOpacity="0.12"
        strokeWidth="1.5"
        strokeLinejoin="round"
        style={{
          top: s.top,
          left: s.left,
          '--rot': `${s.rot}deg`,
          '--dur': `${s.dur}s`,
          '--delay': `${s.delay}s`,
          '--dx': `${s.dx}px`,
          '--dy': `${s.dy}px`,
        }}
      >
        <ShapePath t={s.t} />
      </svg>
    ))}
  </div>
)

export const Label = ({ children }) => (
  <span className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest">{children}</span>
)

export const Card = ({ title, children, className = '' }) => (
  <div className={`bg-[#1c1b1d] border border-white/10 p-6 ${className}`}>
    {title && <p className="font-mono text-[11px] text-neutral-400 uppercase tracking-widest mb-4">{title}</p>}
    {children}
  </div>
)

export const PrimaryButton = ({ children, ...props }) => (
  <button
    {...props}
    className="bg-white text-black px-8 py-3 font-mono text-xs font-bold uppercase tracking-widest hover:bg-neutral-200 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
  >
    {children}
  </button>
)

export const GhostButton = ({ children, ...props }) => (
  <button
    {...props}
    className="px-5 py-2 border border-white/20 font-mono text-[12px] uppercase tracking-widest text-neutral-400 hover:text-white hover:border-white/40 transition-all"
  >
    {children}
  </button>
)

export const PageShell = ({ children }) => (
  <div className="relative min-h-screen bg-[#131315] overflow-hidden">
    <div
      className="absolute inset-0 pointer-events-none opacity-[0.025]"
      style={{
        backgroundImage:
          'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
        backgroundSize: '64px 64px',
      }}
    />
    <FloatingShapes />
    <div className="fixed top-0 right-0 w-[700px] h-[700px] bg-white/[0.025] blur-[140px] rounded-full -translate-y-1/3 translate-x-1/4 pointer-events-none" />
    <div className="relative z-10 px-8 md:px-12 py-10">{children}</div>
  </div>
)

export const PageHeader = ({ kicker, title, right }) => (
  <div className="flex justify-between items-end border-b border-white/10 pb-6 mb-8">
    <div>
      <span className="font-mono text-[0.8rem] text-neutral-400 tracking-widest uppercase mb-2 block">{kicker}</span>
      <h1 className="text-3xl font-bold tracking-tighter uppercase text-white">{title}</h1>
    </div>
    {right}
  </div>
)