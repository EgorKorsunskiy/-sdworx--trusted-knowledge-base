import { TextareaHTMLAttributes, forwardRef } from "react"
import { clsx } from "clsx"

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={clsx(
          "block w-full rounded-lg border-0 bg-white py-2.5 px-3 text-sm text-stone-900 ring-1 ring-inset ring-stone-300 placeholder:text-stone-400 focus:ring-2 focus:ring-stone-900 focus:outline-none",
          className
        )}
        {...props}
      />
    )
  }
)
Textarea.displayName = "Textarea"
