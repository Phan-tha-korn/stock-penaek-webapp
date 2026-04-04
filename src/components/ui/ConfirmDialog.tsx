import { useEffect, useRef, useState, useCallback, createContext, useContext } from 'react'
import { useTranslation } from 'react-i18next'

/* ── Types ─────────────────────────────────────────────────────────────────── */

type DialogKind = 'alert' | 'confirm' | 'prompt'

interface DialogOptions {
  title?: string
  message: string
  kind: DialogKind
  defaultValue?: string
  confirmLabel?: string
  cancelLabel?: string
  placeholder?: string
}

interface DialogResult {
  confirmed: boolean
  value: string
}

type OpenDialogFn = (opts: DialogOptions) => Promise<DialogResult>

/* ── Context ───────────────────────────────────────────────────────────────── */

const DialogContext = createContext<OpenDialogFn | null>(null)

export function useDialog(): OpenDialogFn {
  const fn = useContext(DialogContext)
  if (!fn) throw new Error('useDialog must be used inside <ConfirmDialogProvider>')
  return fn
}

/* Convenience wrappers */
export function useAlert() {
  const dialog = useDialog()
  return useCallback(
    (message: string, title?: string) => dialog({ kind: 'alert', message, title }),
    [dialog],
  )
}

export function useConfirm() {
  const dialog = useDialog()
  return useCallback(
    (message: string, title?: string) =>
      dialog({ kind: 'confirm', message, title }).then((r) => r.confirmed),
    [dialog],
  )
}

export function usePrompt() {
  const dialog = useDialog()
  return useCallback(
    (message: string, defaultValue?: string) =>
      dialog({ kind: 'prompt', message, defaultValue }).then((r) =>
        r.confirmed ? r.value : null,
      ),
    [dialog],
  )
}

/* ── Provider + Dialog UI ──────────────────────────────────────────────────── */

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation()
  const [state, setState] = useState<(DialogOptions & { resolve: (v: DialogResult) => void }) | null>(null)
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  const open: OpenDialogFn = useCallback(
    (opts) =>
      new Promise<DialogResult>((resolve) => {
        setInputValue(opts.defaultValue ?? '')
        setState({ ...opts, resolve })
      }),
    [],
  )

  const close = useCallback(
    (confirmed: boolean) => {
      if (!state) return
      state.resolve({ confirmed, value: inputValue })
      setState(null)
    },
    [state, inputValue],
  )

  useEffect(() => {
    if (state?.kind === 'prompt') {
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [state])

  useEffect(() => {
    if (!state) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [state, close])

  return (
    <DialogContext.Provider value={open}>
      {children}
      {state && (
        <div
          ref={overlayRef}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (e.target === overlayRef.current) close(false)
          }}
          role="dialog"
          aria-modal="true"
          aria-label={state.title || state.message}
        >
          <div className="mx-4 w-full max-w-md rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-6 shadow-2xl">
            {state.title && (
              <h3 className="mb-2 text-lg font-semibold text-[color:var(--color-fg)]">{state.title}</h3>
            )}
            <p className="text-sm text-[color:var(--color-muted)] whitespace-pre-wrap">{state.message}</p>

            {state.kind === 'prompt' && (
              <input
                ref={inputRef}
                className="mt-3 w-full rounded border border-[color:var(--color-border)] bg-black/20 px-3 py-2 text-sm text-[color:var(--color-fg)] outline-none focus:border-[color:var(--color-primary)]"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={state.placeholder ?? ''}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') close(true)
                }}
              />
            )}

            <div className="mt-5 flex justify-end gap-2">
              {state.kind !== 'alert' && (
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-[color:var(--color-fg)] hover:bg-white/5"
                  onClick={() => close(false)}
                  type="button"
                >
                  {state.cancelLabel || t('app.cancel')}
                </button>
              )}
              <button
                className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black hover:opacity-90"
                onClick={() => close(true)}
                type="button"
              >
                {state.confirmLabel || (state.kind === 'alert' ? t('app.close') : t('app.confirm'))}
              </button>
            </div>
          </div>
        </div>
      )}
    </DialogContext.Provider>
  )
}
