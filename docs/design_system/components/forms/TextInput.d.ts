import type { CSSProperties } from 'react';

/**
 * Single-line editable text field.
 * @dsComponent
 */
export interface TextInputProps {
  value?: string;
  placeholder?: string;
  /** px. Engine default 200. */
  width?: number;
  /** Engine's active flag — border switches to secondary and a caret shows. */
  active?: boolean;
  disabled?: boolean;
  /** Engine caps input at 32 characters by default. */
  maxLength?: number;
  /** Render in the mono family — use for paths, ids and numeric fields. */
  mono?: boolean;
  onChange?: (value: string) => void;
  style?: CSSProperties;
}
export function TextInput(props: TextInputProps): JSX.Element;
