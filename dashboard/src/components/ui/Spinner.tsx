import { cn } from '@/lib/utils'

export function Spinner({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center justify-center p-8', className)}>
      <div className="w-8 h-8 border-2 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
    </div>
  )
}

export function InlineSpinner({ className }: { className?: string }) {
  return (
    <div className={cn('w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin', className)} />
  )
}
