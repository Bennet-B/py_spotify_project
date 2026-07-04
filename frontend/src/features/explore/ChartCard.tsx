import type { ReactNode } from 'react'

/** Uniform card around a chart: title row, optional hint about the chart's selection gesture, white surface. */
export function ChartCard({ title, hint, children, className }: { title: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-gray-200 bg-white p-3 ${className ?? ''}`}>
      <div className="mb-1 flex items-baseline justify-between gap-2 px-1">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        {hint !== undefined && <span className="text-xs text-gray-400">{hint}</span>}
      </div>
      {children}
    </section>
  )
}
