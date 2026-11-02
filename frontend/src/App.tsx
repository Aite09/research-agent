/**
 * App.tsx — Research Agent
 *
 * gpt-taste skill — Awwwards-level redesign
 * Hero: Cinematic Center, full-viewport, GSAP word-by-word stagger
 * Components: Infinite Marquee (example queries), Inline Animated Badge, Spotlight Cards
 * GSAP: Hero text reveal + ScrollTrigger paragraph scrub (in ReportDisplay)
 */

import { useState, useRef, useCallback } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { Background } from './components/Background'
import { AgentTimeline } from './components/AgentTimeline'
import { ReportDisplay } from './components/ReportDisplay'
import type { AgentStep, AgentName, PipelineStatus, ResearchResult, WsEvent } from './types'

gsap.registerPlugin()

const WS_URL = 'ws://localhost:8001/ws/research'

const EXAMPLES = [
  'Impact of AI on Toronto job market in 2025',
  'Climate change reshaping Canadian real estate',
  'Most in-demand engineering skills for 2026',
  'How is SpaceX changing commercial spaceflight?',
  'State of quantum computing in 2025',
  'Renewable energy adoption trends worldwide',
  'Future of remote work after 2025',
  'Rise of AI agents in software development',
]

// ── Floating nav ─────────────────────────────────────────────────────────────
function Nav({ showReset, onReset }: { showReset: boolean; onReset: () => void }) {
  return (
    <header
      className="fixed top-5 left-0 right-0 flex justify-center pointer-events-none"
      style={{ zIndex: 40 }}
    >
      <nav
        className="pointer-events-auto flex items-center gap-5 px-5 py-2.5 rounded-full glass"
        style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.05) inset, 0 8px 32px rgba(0,0,0,0.5)' }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, rgba(34,197,94,0.2), rgba(14,165,233,0.15))',
              border: '1px solid rgba(34,197,94,0.2)',
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </div>
          <span className="text-[13px] font-display font-semibold text-slate-200 tracking-tight">
            Research Agent
          </span>
        </div>

        <div className="w-px h-3.5 bg-white/10" />

        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-ring" />
          <span className="text-[11px] text-slate-500 font-mono">Groq · LangGraph</span>
        </div>

        {showReset && (
          <>
            <div className="w-px h-3.5 bg-white/10" />
            <button
              onClick={onReset}
              className="
                flex items-center gap-1.5 px-3 py-1 rounded-full
                text-[11px] font-body text-slate-400 hover:text-slate-200 cursor-pointer
                border border-white/[0.07] hover:border-white/[0.15]
                transition-all duration-300 ease-spring active:scale-[0.98]
              "
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1 4 1 10 7 10"/>
                <path d="M3.51 15a9 9 0 1 0 .49-3.51"/>
              </svg>
              New
            </button>
          </>
        )}
      </nav>
    </header>
  )
}

// ── Infinite marquee — example queries ───────────────────────────────────────
function ExampleMarquee({ onSelect }: { onSelect: (q: string) => void }) {
  const doubled = [...EXAMPLES, ...EXAMPLES]
  return (
    <div
      className="overflow-hidden"
      style={{ maskImage: 'linear-gradient(to right, transparent, black 12%, black 88%, transparent)' }}
    >
      <div className="flex gap-3 animate-marquee w-max py-2">
        {doubled.map((item, i) => (
          <button
            key={i}
            onClick={() => onSelect(item)}
            className="
              flex-shrink-0 px-4 py-2 rounded-full
              border border-white/[0.07] bg-white/[0.02]
              text-[12px] text-slate-500
              hover:text-slate-200 hover:border-emerald-500/30 hover:bg-emerald-500/[0.04]
              transition-all duration-300 cursor-pointer whitespace-nowrap
            "
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Idle section — cinematic center hero ──────────────────────────────────────
interface IdleProps {
  query: string
  setQuery: (v: string) => void
  onSubmit: (q: string) => void
}

function IdleSection({ query, setQuery, onSubmit }: IdleProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useGSAP(() => {
    // Word-by-word stagger on headline
    gsap.from('.gsap-word', {
      opacity: 0,
      y: 52,
      duration: 0.85,
      stagger: 0.07,
      ease: 'power3.out',
      delay: 0.15,
    })
    // Subtitle + badge fade up
    gsap.from('.gsap-sub', {
      opacity: 0,
      y: 22,
      duration: 0.7,
      delay: 0.55,
      stagger: 0.08,
      ease: 'power2.out',
    })
    // Input block
    gsap.from('.gsap-input', {
      opacity: 0,
      y: 22,
      duration: 0.65,
      delay: 0.8,
      ease: 'power2.out',
    })
    // Marquee fade
    gsap.from('.gsap-marquee', {
      opacity: 0,
      duration: 0.5,
      delay: 1.05,
    })
    // Bottom stats
    gsap.from('.gsap-stats', {
      opacity: 0,
      duration: 0.5,
      delay: 1.15,
    })
  }, { scope: containerRef })

  return (
    <div
      ref={containerRef}
      className="min-h-[100dvh] flex flex-col items-center justify-center px-4 pt-24 pb-16"
    >
      {/* Eyebrow badge — inline animated pulse */}
      <div className="gsap-sub mb-7">
        <span
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] uppercase tracking-[0.2em] font-medium text-slate-400"
          style={{
            background: 'rgba(34,197,94,0.06)',
            border: '1px solid rgba(34,197,94,0.2)',
          }}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
          Multi-Agent AI Research
        </span>
      </div>

      {/* Headline — max-w-5xl, clamp font, exactly 2 lines */}
      <h1
        className="text-center font-display font-bold tracking-tight leading-[1.04] max-w-5xl mb-6 w-full"
        style={{ fontSize: 'clamp(2.8rem, 6vw, 5.5rem)' }}
      >
        <span className="gsap-word inline-block text-slate-100">Autonomous</span>{' '}
        <span className="gsap-word inline-block text-slate-100">research,</span>
        <br />
        <span
          className="gsap-word inline-block"
          style={{
            background: 'linear-gradient(135deg, #22c55e 0%, #86efac 55%, #22c55e 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          delivered
        </span>{' '}
        <span className="gsap-word inline-block text-slate-100">in</span>{' '}
        <span className="gsap-word inline-block text-slate-100">minutes.</span>
      </h1>

      {/* Subtitle */}
      <p className="gsap-sub text-center text-slate-500 text-base sm:text-lg leading-relaxed max-w-[46ch] mb-10">
        Four specialised agents — Planner, Search, Writer, Critic — collaborate
        autonomously to produce a self-reviewed report with sources.
      </p>

      {/* Double-bezel search input */}
      <div className="gsap-input w-full max-w-2xl mb-10">
        <form onSubmit={e => { e.preventDefault(); onSubmit(query) }}>
          <div className="bezel-outer">
            <div className="bezel-inner flex items-center gap-2 pr-2">
              <div className="pl-4 text-slate-600 flex-shrink-0">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
              </div>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="What do you want to research?"
                autoFocus
                className="
                  flex-1 bg-transparent py-4 text-sm text-slate-200
                  placeholder-slate-600 outline-none font-body
                "
              />
              {/* Button-in-button CTA */}
              <button
                type="submit"
                disabled={!query.trim()}
                className="
                  group flex items-center gap-2 px-4 py-2 rounded-full
                  font-display font-medium text-sm cursor-pointer
                  disabled:opacity-25 disabled:cursor-not-allowed
                  transition-all duration-300 ease-spring active:scale-[0.97]
                "
                style={{
                  background: query.trim() ? '#22c55e' : 'rgba(255,255,255,0.07)',
                  color: query.trim() ? '#052e16' : '#475569',
                }}
              >
                Research
                <div
                  className="
                    w-6 h-6 rounded-full flex items-center justify-center
                    group-hover:translate-x-0.5 group-hover:-translate-y-px
                    transition-transform duration-300 ease-spring
                  "
                  style={{ background: 'rgba(0,0,0,0.15)' }}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                  </svg>
                </div>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Infinite marquee — example queries */}
      <div className="gsap-marquee w-full max-w-3xl">
        <p className="text-center text-[10px] uppercase tracking-[0.18em] text-slate-700 mb-3">
          Try an example
        </p>
        <ExampleMarquee onSelect={q => onSubmit(q)} />
      </div>

      {/* Bottom pipeline stat strip */}
      <div className="gsap-stats mt-12 flex items-center gap-5 text-[11px] font-mono text-slate-700">
        <span>4 agents</span>
        <span className="w-1 h-1 rounded-full bg-white/[0.12]" />
        <span>Groq LLM</span>
        <span className="w-1 h-1 rounded-full bg-white/[0.12]" />
        <span>Tavily search</span>
        <span className="w-1 h-1 rounded-full bg-white/[0.12]" />
        <span>Self-correcting</span>
      </div>
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [query,    setQuery]    = useState('')
  const [status,   setStatus]   = useState<PipelineStatus>('idle')
  const [steps,    setSteps]    = useState<AgentStep[]>([])
  const [result,   setResult]   = useState<ResearchResult | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [statusTxt,setStatusTxt]= useState('')

  const wsRef = useRef<WebSocket | null>(null)

  const upsertStep = useCallback((agent: AgentName, patch: Partial<AgentStep>) => {
    setSteps(prev => {
      const exists = prev.find(s => s.agent === agent)
      if (exists) return prev.map(s => s.agent === agent ? { ...s, ...patch } : s)
      return [...prev, { agent, status: 'waiting', message: '', ...patch }]
    })
  }, [])

  const handleSubmit = useCallback((q: string) => {
    const trimmed = q.trim()
    if (!trimmed || status === 'running') return

    setQuery(trimmed)
    setStatus('running')
    setSteps([])
    setResult(null)
    setErrorMsg('')
    setStatusTxt('Connecting...')

    wsRef.current?.close()
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setStatusTxt('Pipeline starting...')
      ws.send(JSON.stringify({ query: trimmed }))
    }

    ws.onmessage = (ev: MessageEvent) => {
      const data: WsEvent = JSON.parse(ev.data as string)
      switch (data.type) {
        case 'pipeline_start':
          setStatusTxt(data.message)
          break
        case 'agent_start':
          upsertStep(data.agent, { status: 'running', message: data.message })
          setStatusTxt(`${data.agent} running...`)
          break
        case 'agent_done':
          upsertStep(data.agent, { status: 'done', message: data.message, data: data.data })
          break
        case 'agent_error':
          upsertStep(data.agent, { status: 'error', message: data.error })
          break
        case 'complete':
          setResult({
            report:        data.report,
            quality_score: data.quality_score,
            revision_count:data.revision_count,
            search_queries:data.search_queries,
            word_count:    data.word_count,
            source_count:  data.source_count,
          })
          setStatus('done')
          setStatusTxt('Complete')
          setSteps(prev => prev.map(s => s.status === 'running' ? { ...s, status: 'done' } : s))
          ws.close()
          break
        case 'error':
          setErrorMsg(data.message)
          setStatus('error')
          setStatusTxt('Error')
          ws.close()
          break
      }
    }

    ws.onerror = () => {
      setErrorMsg('Connection failed. Is the backend running? → uvicorn api.main:app --reload')
      setStatus('error')
    }
  }, [status, upsertStep])

  const handleReset = () => {
    wsRef.current?.close()
    setQuery('')
    setStatus('idle')
    setSteps([])
    setResult(null)
    setErrorMsg('')
    setStatusTxt('')
  }

  return (
    <main className="overflow-x-hidden w-full max-w-full relative min-h-[100dvh] font-body">
      <Background />

      <div className="relative" style={{ zIndex: 2 }}>
        <Nav showReset={status !== 'idle'} onReset={handleReset} />

        {/* ── IDLE ─────────────────────────────────────────────────────────── */}
        {status === 'idle' && (
          <IdleSection query={query} setQuery={setQuery} onSubmit={handleSubmit} />
        )}

        {/* ── RUNNING / DONE / ERROR ────────────────────────────────────────── */}
        {(status === 'running' || status === 'done' || status === 'error') && (
          <div className="max-w-7xl mx-auto px-4 sm:px-8 pt-28 pb-16">

            {/* Query banner */}
            <div className="reveal mb-6 flex items-start gap-3 px-4 py-3 rounded-xl border border-white/[0.06] bg-white/[0.02]">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-shrink-0">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <p className="text-sm text-slate-300 leading-snug flex-1">{query}</p>
              {status === 'running' && (
                <span className="flex items-center gap-1.5 text-[11px] text-emerald-500/70 font-mono flex-shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  {statusTxt}
                </span>
              )}
              {status === 'done' && (
                <span className="text-[11px] text-emerald-500 font-mono flex-shrink-0">Done</span>
              )}
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6 items-start">

              {/* Left — sticky timeline */}
              <div className="reveal lg:sticky lg:top-24 lg:self-start">
                <div
                  className="rounded-2xl border p-4"
                  style={{
                    background: 'rgba(10,15,30,0.75)',
                    borderColor: 'rgba(255,255,255,0.07)',
                    backdropFilter: 'blur(20px)',
                  }}
                >
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] uppercase tracking-widest text-slate-600">Agents</span>
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-600">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/50 animate-pulse" />
                      live
                    </div>
                  </div>
                  <AgentTimeline steps={steps} />
                </div>
              </div>

              {/* Right — report / skeleton / error */}
              <div className="min-w-0">

                {/* Skeleton while running */}
                {status === 'running' && !result && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-4 gap-3">
                      {[...Array(4)].map((_, i) => (
                        <div key={i} className="bezel-outer">
                          <div className="bezel-inner h-14 shimmer-bar rounded-[calc(1.25rem-5px)]" />
                        </div>
                      ))}
                    </div>
                    <div className="bezel-outer">
                      <div className="bezel-inner p-6 space-y-3">
                        {[85, 60, 90, 50, 72, 80, 55].map((w, i) => (
                          <div key={i} className="h-2.5 rounded-full shimmer-bar" style={{ width: `${w}%` }} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Error state */}
                {status === 'error' && (
                  <div
                    className="reveal rounded-2xl border p-6 space-y-3"
                    style={{ background: 'rgba(239,68,68,0.05)', borderColor: 'rgba(239,68,68,0.2)' }}
                  >
                    <div className="flex items-center gap-2">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                      </svg>
                      <span className="text-sm font-display font-semibold text-red-400">Pipeline Error</span>
                    </div>
                    <p className="text-sm text-red-300/70 leading-relaxed">{errorMsg}</p>
                  </div>
                )}

                {/* Report */}
                {result && <ReportDisplay result={result} />}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
