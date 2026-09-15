import type { CSSProperties, ReactNode } from 'react';

/**
 * Linear layout container — the engine's only layout primitive.
 * @dsComponent
 */
export interface BoxContainerProps {
  /** Engine LayoutDirection. Default VERTICAL. */
  direction?: 'VERTICAL' | 'HORIZONTAL';
  /** Engine LayoutAlignment on the main axis. Default START. */
  align?: 'START' | 'CENTER' | 'END' | 'STRETCH';
  /** px between children. Engine default 5. */
  spacing?: number;
  /** The engine always centres children on the cross axis; set false to opt out. */
  crossCenter?: boolean;
  style?: CSSProperties;
  children?: ReactNode;
}
export function BoxContainer(props: BoxContainerProps): JSX.Element;
