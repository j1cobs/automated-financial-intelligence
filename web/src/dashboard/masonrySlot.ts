/**
 * The contract between `MasonryColumns` and the card bodies inside it. Kept
 * apart from the components so that file only exports components (React
 * Refresh needs that to hot-reload them).
 *
 * Each pool slot provides a `SlotApi`; a `ScrollBody` inside the card registers
 * the elements the layout needs to measure. A card with no `ScrollBody` never
 * registers and is laid out as a fixed block, exactly as before Phase 36.
 */

import { createContext, useContext } from 'react';

export interface BodyRegistration {
  /** The scroll container: its `clientHeight` separates the card's overhead from its body. */
  outer: HTMLDivElement;
  /** The `Stack` whose rows are measured; null for an elastic (chart) body. */
  stack: HTMLElement | null;
  minBody: number;
  /** Declared natural chart height; present only for elastic bodies. */
  elasticHeight?: number;
}

export interface SlotApi {
  register(registration: BodyRegistration | null): void;
}

export const MasonrySlotContext = createContext<SlotApi | null>(null);

/** Set by `ScrollBody` for the `Stack` inside it; null outside a pool slot. */
export const StackRefContext = createContext<((el: HTMLElement | null) => void) | null>(null);

/** True inside a `MasonryColumns` slot, where a card's body is sized by the layout. */
export function useInMasonrySlot(): boolean {
  return useContext(MasonrySlotContext) !== null;
}
