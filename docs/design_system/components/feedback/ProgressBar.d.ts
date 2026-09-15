import type { CSSProperties } from 'react';

/**
 * Visualises progress from 0.0 to 1.0 as a left-anchored fill.
 * @dsComponent
 * @startingPoint section="Feedback" subtitle="Health, stamina and load bars" viewport="700x160"
 */
export interface ProgressBarProps {
  /** Clamped 0.0-1.0 by the engine. */
  value?: number;
  /** px. Engine default 200. */
  width?: number;
  /** px. Engine default 20. */
  height?: number;
  /** Defaults to the theme secondary, as in the engine. */
  fillColor?: string;
  bgColor?: string;
  /** Optional monospace caption to the right of the bar. */
  label?: string;
  style?: CSSProperties;
}
export function ProgressBar(props: ProgressBarProps): JSX.Element;
