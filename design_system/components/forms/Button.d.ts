import type { CSSProperties, ReactNode } from 'react';

/**
 * Clickable button with the engine's five visual states.
 * @dsComponent
 * @startingPoint section="Forms" subtitle="Menu and editor buttons, all skins" viewport="700x260"
 */
export interface ButtonProps {
  /** Label text. Rendered uppercase in the pixel family. */
  text?: string;
  children?: ReactNode;
  /** primary/secondary/ghost are UI skins; wood and sage are the in-game menu plates from the spritesheet. */
  variant?: 'primary' | 'secondary' | 'wood' | 'sage' | 'ghost';
  /** small = 30px, normal = 40px (engine default), large = 52px. */
  size?: 'small' | 'normal' | 'large';
  disabled?: boolean;
  /** Renders the engine's FOCUSED state — border switches to secondary. */
  focused?: boolean;
  fullWidth?: boolean;
  /** Inner bevel highlight/shadow. On by default. */
  bevel?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}
export function Button(props: ButtonProps): JSX.Element;
