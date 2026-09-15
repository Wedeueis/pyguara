import type { CSSProperties } from 'react';

/**
 * Read-only text. The engine's Label auto-sizes to its content.
 * @dsComponent
 */
export interface LabelProps {
  text: string;
  /** px. The engine ships 12 / 16 / 24 / 32. */
  fontSize?: number;
  color?: string;
  /** Which brand family to render in. */
  font?: 'pixel' | 'display' | 'body' | 'mono';
  uppercase?: boolean;
  /** Engine UIAnchor name — only the horizontal part affects text alignment. */
  anchor?: 'TOP_LEFT' | 'TOP_CENTER' | 'TOP_RIGHT' | 'CENTER_LEFT' | 'CENTER' | 'CENTER_RIGHT' | 'BOTTOM_LEFT' | 'BOTTOM_CENTER' | 'BOTTOM_RIGHT';
  style?: CSSProperties;
}
export function Label(props: LabelProps): JSX.Element;
