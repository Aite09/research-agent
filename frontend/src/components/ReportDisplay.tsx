/**
 * ReportDisplay.tsx
 *
 * Renders the final research report.
 * GSAP ScrollTrigger: paragraph-by-paragraph scrub reveal as user scrolls.
 * GSAP stagger: stat cards and quality bar animate in on mount.
 * Stats grid, quality score bar, copy-to-clipboard.
 */

import { useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import type { ResearchResult } from '../types'

gsap.registerPlugin(ScrollTrigger)

// ── Stat card ───────────────────────────────────────────────────────────────
function StatCard({ label, value, unit = '' }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="gsap-stat bezel-outer cursor-default">
      <div className="bezel-inner px-4 py-3">
        <div className="text-[10px] uppercase tracking-widest text-slate-600 font-body mb-1">{label}</div>
        <div className="text-xl font-display font-bold text-slate-100 leading-none">
          {value}
          <span className="text-sm text-slate-500 font-normal ml-0.5">{unit}</span>
        </div>
      </div>
    </div>
  )
}

// ── Quality score bar ───────────────────────────────────────────────────────
function QualityBar({ score }: { score: number }) {
  const pct   = (score / 10) * 100
  const color = score >= 8 ? '#22c55e' : score >= 6 ? '#f59e0b' : '#ef4444'
  const label = score >= 8 ? 'Excellent' : score >= 6 ? 'Good' : 'Needs work'

  return (
    <div className="gsap-quality bezel-outer">
      <div className="bezel-inner px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase tracking-widest text-slate-600 font-body">
            Quality Score
          </span>
          <span className="text-sm font-mono" style={{ color }}>
            {score}/10 · {label}
          </span>
        </div>
        <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-1000 ease-spring"
            style={{ width: `${pct}%`, background: color, boxShadow: `0 0 8px ${color}60` }}
          />
        </div>
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
interface Props { result: ResearchResult }

export function ReportDisplay({ result }: Props) {
  const { report, quality_score, revision_count, word_count, source_count, search_queries } = result
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const ctx = gsap.context(() => {
      // Stat cards stagger in
      gsap.from('.gsap-stat', {
        opacity: 0,
        y: 24,
        duration: 0.55,
        stagger: 0.08,
        ease: 'back.out(1.5)',
      })

      // Quality bar fade up
      gsap.from('.gsap-quality', {
        opacity: 0,
        y: 16,
        duration: 0.5,
        delay: 0.38,
        ease: 'power2.out',
      })

      // Report card fade up
      gsap.from('.gsap-report-card', {
        opacity: 0,
        y: 24,
        duration: 0.6,
        delay: 0.5,
        ease: 'power2.out',
      })

      // ScrollTrigger: scrub-reveal each paragraph/heading as user scrolls
      // Gives the "text materialising as you read" cinematic effect
      const elements = gsap.utils.toArray<HTMLElement>('.md p, .md h2, .md h3, .md li, .md blockquote')
      elements.forEach(el => {
        gsap.from(el, {
          opacity: 0,
          y: 14,
          duration: 0.55,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: el,
            start: 'top 90%',
            toggleActions: 'play none none none',
          },
        })
      })
    }, containerRef)

    return () => ctx.revert()
  }, [result])

  function copyReport() {
    navigator.clipboard.writeText(report).catch(() => {})
  }

  return (
    <div ref={containerRef} className="space-y-4">

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Words"     value={word_count.toLocaleString()} />
        <StatCard label="Sources"   value={source_count} />
        <StatCard label="Queries"   value={search_queries.length} />
        <StatCard label="Revisions" value={revision_count} />
      </div>

      {/* Quality bar */}
      <QualityBar score={quality_score} />

      {/* Report card */}
      <div className="gsap-report-card bezel-outer">
        <div className="bezel-inner px-6 py-6">

          {/* Header row */}
          <div className="flex items-center justify-between mb-5 pb-4 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-xs text-slate-500 font-body uppercase tracking-widest">
                Research Report
              </span>
            </div>
            <button
              onClick={copyReport}
              className="
                group flex items-center gap-2 px-3 py-1.5 rounded-full
                border border-white/[0.07] hover:border-white/[0.14]
                text-[11px] text-slate-500 hover:text-slate-300
                transition-all duration-300 ease-spring cursor-pointer
                active:scale-[0.97]
              "
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              Copy
            </button>
          </div>

          {/* Markdown content — GSAP ScrollTrigger targets .md children */}
          <div className="md">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report}
            </ReactMarkdown>
          </div>

        </div>
      </div>
    </div>
  )
}
