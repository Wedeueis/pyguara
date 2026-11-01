import React from 'react';

/* Mirrors pyguara/ui/components/checkbox.py. Source geometry is fixed:
   a 20px box, a 10px inner square in theme.colors.secondary when checked,
   5px between box and label, 1px border. Hover lightens the box by 20/channel. */
export function Checkbox({label,checked=false,disabled=false,onChange,style,...rest}){
  return <label style={{
    display:'inline-flex',alignItems:'center',gap:'5px',
    fontFamily:'var(--font-pixel)',fontSize:'16px',letterSpacing:'var(--ls-pixel)',
    color:disabled?'var(--text-on-disabled)':'var(--text-body)',
    cursor:disabled?'not-allowed':'pointer',...style,
  }} {...rest}>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange&&onChange(e.target.checked)} style={{position:'absolute',opacity:0,width:0,height:0}} />
    <span aria-hidden="true" style={{
      width:'var(--size-checkbox)',height:'var(--size-checkbox)',flex:'0 0 auto',
      background:'var(--surface-inset)',border:'1px solid var(--edge-strong)',
      display:'grid',placeItems:'center',
    }}>
      {checked&&<span style={{width:'10px',height:'10px',background:disabled?'var(--action-disabled)':'var(--action-secondary)',display:'block'}} />}
    <\/span>
    {label}
  <\/label>;
}
