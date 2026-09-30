import { SelectHTMLAttributes, forwardRef } from "react"
import { clsx } from "clsx"

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={clsx(
          "block w-full rounded-lg border-0 bg-white py-2.5 px-3 text-sm text-stone-900 ring-1 ring-inset ring-stone-300 focus:ring-2 focus:ring-stone-900 focus:outline-none appearance-none",
          className
        )}
        {...props}
      >
        {children}
      </select>
    )
  }
)
Select.displayName = "Select"
