import type { CSSProperties } from 'react';

/**
 * Draggable value selector with a circular knob on a 2px track.
 * @dsComponent
 */
export interface SliderProps {
  value?: number;
  /** Engine defaults are 0.0 and 1.0. */
  min?: number;
  max?: number;
  /** 0 means continuous, matching the engine's step default. */
  step?: number;
  /** px. Engine default 150. */
  width?: number;
  disabled?: boolean;
  /** Appends a monospace numeric readout. */
  showValue?: boolean;
  onChange?: (value: number) => void;
  style?: CSSProperties;
}
export function Slider(props: SliderProps): JSX.Element;
