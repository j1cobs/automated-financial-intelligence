/**
 * The dashboard's only button primitive.
 *
 * Every button in `web/src` was previously inline Tailwind, which is why ~12 of
 * them shipped without `cursor-pointer` or a hover state: there was no single
 * place for those to live, so each new button re-derived them from scratch and
 * some didn't. Centralising the affordances here makes the bug unrepeatable —
 * a button written with this component cannot fail to look clickable.
 *
 * Variants are about emphasis, not colour-picking: `primary` for the one action
 * a view is for, `secondary` for ordinary controls, `ghost` for low-weight
 * actions sitting inside dense UI (filter chips, "Clear all"), `danger` for
 * destructive ones. All four draw from the existing tokens in `index.css`, so
 * light/dark is handled by the token layer rather than per-variant overrides.
 */

import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

/** Affordances every variant inherits. Exported so tests can assert the
 *  contract directly rather than inferring it from one rendered variant. */
export const BUTTON_BASE_CLASSES = [
  'inline-flex items-center justify-center gap-1',
  'rounded-md font-medium',
  'cursor-pointer transition-colors',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cat-1',
  'disabled:cursor-not-allowed disabled:opacity-60',
].join(' ');

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'min-h-8 px-2 py-1 text-xs',
  md: 'min-h-9 px-3 py-1 text-sm',
};

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'border border-cat-1 bg-cat-1 text-on-emphasis hover:opacity-90',
  secondary: 'border border-hairline bg-surface-1 text-ink hover:bg-surface-2',
  ghost: 'text-ink-secondary hover:bg-surface-2 hover:text-ink',
  danger: 'border border-hairline bg-surface-1 text-flow-expense hover:bg-surface-2',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children?: ReactNode;
  /** React 19 treats `ref` as an ordinary prop for function components, so this
   *  needs declaring but not `forwardRef`. Callers use it to restore focus to
   *  the trigger after closing a popover. */
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  type,
  children,
  ref,
  ...rest
}: ButtonProps) {
  const classes = [BUTTON_BASE_CLASSES, SIZE_CLASSES[size], VARIANT_CLASSES[variant], className ?? '']
    .filter(Boolean)
    .join(' ')
    .trim();

  return (
    // Defaulting to "button" matters: a bare <button> inside a form submits it,
    // and several of these sit next to filter inputs.
    <button type={type ?? 'button'} ref={ref} className={classes} {...rest}>
      {children}
    </button>
  );
}
