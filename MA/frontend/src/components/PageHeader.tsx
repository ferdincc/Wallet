import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  icon?: LucideIcon
  badge?: string
  /** Ek aksan rengi */
  accent?: 'cyan' | 'violet' | 'emerald' | 'amber'
  /** Sağ üst (ör. yenile butonu) */
  actions?: ReactNode
}

const accentMap = {
  cyan: 'from-crypto-cyan/20 via-transparent to-crypto-violet/15',
  violet: 'from-crypto-violet/25 via-transparent to-crypto-cyan/10',
  emerald: 'from-emerald-500/15 via-transparent to-crypto-cyan/10',
  amber: 'from-amber-500/15 via-transparent to-orange-500/10',
}

export default function PageHeader({
  title,
  subtitle,
  icon: Icon,
  badge,
  accent = 'cyan',
  actions,
}: PageHeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="relative mb-8 overflow-hidden rounded-2xl border border-white/[0.08] bg-zinc-900/40 p-6 shadow-xl shadow-black/20 backdrop-blur-xl sm:p-8"
    >
      <div
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accentMap[accent]} opacity-90`}
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -right-20 -top-20 h-40 w-40 rounded-full bg-crypto-cyan/20 blur-3xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -bottom-16 -left-10 h-32 w-32 rounded-full bg-crypto-violet/25 blur-3xl"
        aria-hidden
      />

      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          {Icon && (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 shadow-inner">
              <Icon className="h-6 w-6 text-crypto-cyan" strokeWidth={1.75} />
            </div>
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">{title}</h1>
              {badge && (
                <span className="rounded-full border border-crypto-cyan/30 bg-crypto-cyan/10 px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider text-crypto-cyan">
                  {badge}
                </span>
              )}
            </div>
            {subtitle && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-zinc-400">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2 sm:pt-1">{actions}</div>}
      </div>
    </motion.header>
  )
}
