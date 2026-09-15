import type { CSSProperties, ReactNode } from 'react';

/**
 * Generic drawing surface for mini-maps, model previews and graphs.
 * @dsComponent
 */
export interface CanvasProps {
  width?: number;
  height?: number;
  bgColor?: string;
  /** Overlays the editor's 32px tile grid. */
  grid?: boolean;
  style?: CSSProperties;
  children?: ReactNode;
}
export function Canvas(props: CanvasProps): JSX.Element;
