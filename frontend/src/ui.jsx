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