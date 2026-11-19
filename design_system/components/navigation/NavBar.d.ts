import type { CSSProperties, ReactNode } from 'react';

/**
 * Horizontal bar for the top of a screen: a Panel background plus a row layout.
 * @dsComponent
 * @startingPoint section="Navigation" subtitle="Top bar with brand and actions" viewport="700x140"
 */
export interface NavBarProps {
  /** px. Engine default 50. */
  height?: number;
  /** px between children. Engine default 10. */
  spacing?: number;
  /** Engine LayoutAlignment. Default START. */
  align?: 'START' | 'CENTER' | 'END' | 'STRETCH';
  /** Leading slot, set apart from the rest of the row. */
  brand?: ReactNode;
  children?: ReactNode;
  style?: CSSProperties;
}
export function NavBar(props: NavBarProps): JSX.Element;
