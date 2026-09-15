import React from 'react';

/* Mirrors pyguara/ui/components/text_input.py. Source: 200x30 box, 5px text
   padding, 1px border that switches to theme.colors.secondary when active,
   placeholder drawn in theme.colors.border (dim), max_length 32. */
export function TextInput({value='',placeholder='',width=200,active=false,disabled=false,maxLength=32,mono=false,onChange,style,...rest}){
  return <input type="text" value={value} placeholder={placeholder} disabled={disabled} maxLength={maxLength}
    onChange={e=>onChange&&onChange(e.target.value)}
    style={{
      width:width+'px',height:'var(--size-input-h)',padding:'0 5px',boxSizing:'border-box',
      background:'var(--surface-inset)',
      color:disabled?'var(--text-on-disabled)':'var(--text-body)',
      border:`1px solid ${active?'var(--action-secondary)':'var(--edge-strong)'}`,
      borderRadius:'var(--radius-0)',
      fontFamily:mono?'var(--font-mono)':'var(--font-pixel)',fontSize:'16px',
      letterSpacing:mono?'0':'var(--ls-pixel)',
      outline:'none',...style,
    }} {...rest} />;
}
