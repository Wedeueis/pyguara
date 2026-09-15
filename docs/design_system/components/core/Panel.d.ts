import type { CSSProperties, ReactNode, ElementType } from 'react';

/**
 * Container background: a filled rectangle with a 1px border.
 * @dsComponent
 * @startingPoint section="Core" subtitle="Bordered container surface" viewport="700x200"
 */
export interface PanelProps {
  /** Background fill. Defaults to the theme surface. */
  color?: string;
  /** Border width in px. Engine default is 1. */
  borderWidth?: number;
  /** Inner padding. Defaults to the engine's 8px UI padding. */
  padding?: string;
  /** Adds the pixel-art inner bevel (light top edge, dark bottom edge). */
  bevel?: boolean;
  as?: ElementType;
  style?: CSSProperties;
  children?: ReactNode;
}
export function Panel(props: PanelProps): JSX.Element;
