import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
}

export function Button({
  children,
  className,
  variant = 'primary',
  size = 'md',
  ...props
}: Props) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none',
        size === 'sm' && 'h-8 px-3 text-sm',
        size === 'md' && 'h-10 px-4 text-sm',
        variant === 'primary' && 'bg-stone-900 text-white hover:bg-stone-800',
        variant === 'secondary' &&
          'bg-white text-stone-900 ring-1 ring-stone-200 hover:bg-stone-50',
        variant === 'ghost' && 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export function PrimaryButton(props: Omit<Props, 'variant'>) {
  return <Button variant="primary" {...props} />
}

export function SecondaryButton(props: Omit<Props, 'variant'>) {
  return <Button variant="secondary" {...props} />
}
