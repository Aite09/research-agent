/**
 * Background.tsx
 *
 * Fixed animated background: floating radial gradient orbs + noise overlay.
 * Completely isolated from main render tree — no state, no re-renders.
 * Uses CSS keyframes only (GPU-safe, no JS scroll listeners).
 */

export function Background() {
  return (
    <>
      {/* Animated orbs — transform-only animations (GPU composited) */}
      <div
        aria-hidden="true"
        className="fixed inset-0 overflow-hidden pointer-events-none"
        style={{ zIndex: 0 }}
      >
        {/* Orb 1: emerald, top-right */}
        <div
          className="animate-orb-1 absolute"
          style={{
            top: '-10%',
            right: '-5%',
            width: '55vw',
            height: '55vw',
            maxWidth: 700,
            maxHeight: 700,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(34,197,94,0.09) 0%, transparent 70%)',
            willChange: 'transform',
          }}
        />
        {/* Orb 2: blue, bottom-left */}
        <div
          className="animate-orb-2 absolute"
          style={{
            bottom: '-15%',
            left: '-10%',
            width: '60vw',
            height: '60vw',
            maxWidth: 750,
            maxHeight: 750,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(14,165,233,0.07) 0%, transparent 70%)',
            willChange: 'transform',
          }}
        />
        {/* Orb 3: emerald soft, center */}
        <div
          className="animate-orb-3 absolute"
          style={{
            top: '40%',
            left: '40%',
            width: '40vw',
            height: '40vw',
            maxWidth: 500,
            maxHeight: 500,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(34,197,94,0.04) 0%, transparent 70%)',
            willChange: 'transform',
          }}
        />
      </div>

      {/* Noise grain overlay — fixed, pointer-events-none (no scroll repaint) */}
      <div
        aria-hidden="true"
        className="fixed inset-0 pointer-events-none opacity-[0.025]"
        style={{
          zIndex: 1,
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
          backgroundRepeat: 'repeat',
          backgroundSize: '160px 160px',
        }}
      />
    </>
  )
}
