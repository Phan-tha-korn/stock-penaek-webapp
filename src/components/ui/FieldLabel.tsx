import type { ReactNode } from 'react'

import { HelpHint } from './HelpHint'

export function FieldLabel(props: {
  label: string
  helper?: string
  helpKey?: string
  example?: string
  children: ReactNode
}) {
  return (
    <label className="block space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-[color:var(--color-fg)]">{props.label}</span>
        {props.helpKey ? <HelpHint helpKey={props.helpKey} /> : null}
      </div>
      {props.helper ? <div className="text-xs text-[color:var(--color-muted)]">{props.helper}</div> : null}
      {props.example ? <div className="text-[11px] text-[color:var(--color-muted-strong)]">{props.example}</div> : null}
      {props.children}
    </label>
  )
}
