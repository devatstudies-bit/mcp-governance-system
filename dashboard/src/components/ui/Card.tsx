import { cn } from '@/lib/utils'

interface CardProps {
  children: React.ReactNode
  className?: string
  padding?: boolean
}

export function Card({ children, className, padding = true }: CardProps) {
  return (
    <div className={cn(
      'bg-white rounded-xl border border-gray-200 shadow-sm',
      padding && 'p-5',
      className,
    )}>
      {children}
    </div>
  )
}

interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: React.ReactNode
  color?: 'default' | 'red' | 'orange' | 'green' | 'blue' | 'purple'
  trend?: { value: number; label: string }
}

const COLOR_MAP = {
  default: { icon: 'bg-gray-100 text-gray-600', ring: '' },
  red:     { icon: 'bg-red-100 text-red-600',   ring: 'border-red-100' },
  orange:  { icon: 'bg-orange-100 text-orange-600', ring: 'border-orange-100' },
  green:   { icon: 'bg-green-100 text-green-600',  ring: 'border-green-100' },
  blue:    { icon: 'bg-blue-100 text-blue-600',    ring: 'border-blue-100' },
  purple:  { icon: 'bg-purple-100 text-purple-600', ring: 'border-purple-100' },
}

export function StatCard({ label, value, sub, icon, color = 'default', trend }: StatCardProps) {
  const c = COLOR_MAP[color]
  return (
    <Card className={cn('border', c.ring)}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 truncate">{value}</p>
          {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
          {trend && (
            <p className={cn(
              'mt-1 text-xs font-medium',
              trend.value > 0 ? 'text-red-500' : 'text-green-500',
            )}>
              {trend.value > 0 ? '↑' : '↓'} {Math.abs(trend.value)}% {trend.label}
            </p>
          )}
        </div>
        {icon && (
          <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0', c.icon)}>
            {icon}
          </div>
        )}
      </div>
    </Card>
  )
}
