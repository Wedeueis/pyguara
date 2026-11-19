import type { CSSProperties } from 'react';

/**
 * Displays a texture, optionally tinted.
 * @dsComponent
 */
export interface ImageProps {
  src: string;
  alt?: string;
  width?: number;
  height?: number;
  /** Multiply tint, matching the engine's tint_color. */
  tint?: string;
  /** Keep hard pixel edges on upscale. Default true — turn off only for photos. */
  pixelated?: boolean;
  style?: CSSProperties;
}
export function Image(props: ImageProps): JSX.Element;
