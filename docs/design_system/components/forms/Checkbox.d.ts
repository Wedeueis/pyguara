import type { CSSProperties } from 'react';

/**
 * Boolean toggle: a 20px box with a 10px inner fill, plus a label.
 * @dsComponent
 */
export interface CheckboxProps {
  label: string;
  checked?: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
  style?: CSSProperties;
}
export function Checkbox(props: CheckboxProps): JSX.Element;
