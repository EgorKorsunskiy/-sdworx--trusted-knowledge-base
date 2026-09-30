import { clsx } from "clsx"
import { ReactNode } from "react"

interface BadgeProps {
  children: ReactNode
  variant?: "verified" | "unverified" | "outdated" | "neutral" | "success" | "warning" | "danger"
  className?: string
}

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ring-1 ring-inset",
        variant === "verified" && "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
        variant === "success" && "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
        variant === "unverified" && "bg-amber-50 text-amber-800 ring-amber-600/20",
        variant === "warning" && "bg-amber-50 text-amber-800 ring-amber-600/20",
        variant === "outdated" && "bg-red-50 text-red-700 ring-red-600/20",
        variant === "danger" && "bg-red-50 text-red-700 ring-red-600/20",
        variant === "neutral" && "bg-stone-100 text-stone-600 ring-stone-500/10",
        className
      )}
    >
      {children}
    </span>
  )
}
