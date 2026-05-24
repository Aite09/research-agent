/**
 * AgentTimeline.tsx
 *
 * Premium agent status timeline.
 * GSAP: stagger entry on mount (x: -16 → 0, opacity 0 → 1)
 * Double-bezel cards per step, live connector lines, spring-physics CSS transitions.
 */

import { useRef } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import type { AgentStep, AgentName } from '../types'

// ── Agent metadata ──────────────────────────────────────────────────────────
const AGENT_META: Record<AgentName, { label: string; desc: string; icon: JSX.Element }> = {
  planner: {
    label: 'Planner',
    desc: 'Decompose query into sub-searches',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
        <rect x="9" y="3" width="6" height="4" rx="2"/>
        <line x1="9" y1="12" x2="15" y2="12"/>
        <line x1="9" y1="16" x2="12" y2="16"/>
      </svg>
    ),
  },
  search: {
    label: 'Search',
    desc: 'Fetch web results via Tavily',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  writer: {
    label: 'Writer',
    desc: 'Synthesise results into report',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
      </svg>
    ),
  },
  critic: {
    label: 'Critic',
    desc: 'Score quality, request revisions',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
      </svg>
    ),
  },
}

// ── Status dot ──────────────────────────────────────────────────────────────
function StatusDot({ status }: { status: AgentStep['status'] }) {
  if (status === 'done') {
    return (
      <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center animate-bounce-in">
        <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="2,6 5,9 10,3"/>
        </svg>
      </div>
    )
  }
  if (status === 'running') {
    return (
      <div className="relative w-5 h-5 flex items-center justify-center">
        <div className="absolute w-5 h-5 rounded-full border border-emerald-500/30 animate-pulse-ring" />
        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div className="w-5 h-5 rounded-full bg-red-500/20 border border-red-500/50 flex items-center justify-center animate-bounce-in">
        <svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round">
          <line x1="2" y1="2" x2="10" y2="10"/>
          <line x1="10" y1="2" x2="2" y2="10"/>
        </svg>
      </div>
    )
  }
  return <div className="w-5 h-5 rounded-full border border-white/10 bg-white/[0.03]" />
}

// ── Step card ───────────────────────────────────────────────────────────────
function StepCard({
  step,
  isLast,
}: {
  step: { agent: AgentName; status: AgentStep['status']; message: string; data?: Record<string, unknown> }
  isLast: boolean
}) {
  const meta      = AGENT_META[step.agent]
  const isDone    = step.status === 'done'
  const isRunning = step.status === 'running'
  const isWaiting = step.status === 'waiting'

  return (
    <div className="gsap-step flex gap-3">
      {/* Connector column */}
      <div className="flex flex-col items-center flex-shrink-0 pt-0.5">
        <StatusDot status={step.status} />
        {!isLast && (
          <div
            className="w-px flex-1 min-h-[28px] mt-1.5 transition-colors duration-700"
            style={{
              background: isDone
                ? 'linear-gradient(to bottom, rgba(34,197,94,0.5), rgba(34,197,94,0.1))'
                : isRunning
                ? 'linear-gradient(to bottom, rgba(34,197,94,0.3), rgba(255,255,255,0.05))'
                : 'rgba(255,255,255,0.06)',
            }}
          />
        )}
      </div>

      {/* Card */}
      <div
        className={`
          mb-3 flex-1 min-w-0 rounded-xl border transition-all duration-500
          ${isRunning
            ? 'border-emerald-500/20 bg-emerald-500/[0.04] shadow-[0_0_20px_rgba(34,197,94,0.05)]'
            : isDone
            ? 'border-white/[0.06] bg-white/[0.02]'
            : 'border-white/[0.04] bg-transparent'
          }
        `}
        style={{ padding: isWaiting ? '0.6rem 0.85rem' : '0.75rem 0.85rem' }}
      >
        <div className="flex items-center gap-2 mb-0.5">
          <span
            className={`transition-colors duration-500 ${
              isDone ? 'text-emerald-500' : isRunning ? 'text-emerald-400' : 'text-slate-600'
            }`}
          >
            {meta.icon}
          </span>
          <span
            className={`text-xs font-semibold font-display tracking-wide transition-colors duration-500 ${
              isDone ? 'text-slate-300' : isRunning ? 'text-slate-200' : 'text-slate-600'
            }`}
          >
            {meta.label}
          </span>
          {isRunning && (
            <span className="text-[10px] text-emerald-400/70 font-mono ml-auto animate-pulse">
              running
            </span>
          )}
        </div>

        {(isRunning || isDone) && step.message && (
          <p className="text-[11px] text-slate-500 leading-snug">{step.message}</p>
        )}
        {isWaiting && (
          <p className="text-[11px] text-slate-700 leading-snug">{meta.desc}</p>
        )}

        {isDone && step.data && (
          <div className="mt-1.5 font-mono text-[10px] text-emerald-600/70">
            {step.agent === 'planner' && `${(step.data as { search_queries?: string[] }).search_queries?.length ?? 0} sub-queries`}
            {step.agent === 'search'  && `${(step.data as { result_count?: number }).result_count ?? 0} results`}
            {step.agent === 'writer'  && `${(step.data as { word_count?: number }).word_count ?? 0} words`}
            {step.agent === 'critic'  && `${(step.data as { quality_score?: number }).quality_score ?? 0}/10 quality`}
          </div>
        )}

        {isRunning && (
          <div className="mt-2 h-0.5 rounded-full overflow-hidden bg-white/[0.04]">
            <div className="h-full shimmer-bar rounded-full" />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
interface Props { steps: AgentStep[] }

const ALL_AGENTS: AgentName[] = ['planner', 'search', 'writer', 'critic']

export function AgentTimeline({ steps }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  // GSAP stagger entry — runs once on mount
  useGSAP(() => {
    gsap.from('.gsap-step', {
      opacity: 0,
      x: -18,
      duration: 0.55,
      stagger: 0.09,
      ease: 'power2.out',
    })
  }, { scope: containerRef })

  return (
    <div ref={containerRef}>
      {ALL_AGENTS.map((agent, i) => {
        const step = steps.find(s => s.agent === agent) ?? {
          agent,
          status: 'waiting' as const,
          message: '',
        }
        return (
          <StepCard
            key={agent}
            step={step}
            isLast={i === ALL_AGENTS.length - 1}
          />
        )
      })}
    </div>
  )
}
