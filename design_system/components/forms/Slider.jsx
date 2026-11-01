import React from 'react';

/* Mirrors pyguara/ui/components/slider.py. Source: a 2px track line in
   theme.colors.border across the full width, and a radius-8 circular knob in
   theme.colors.secondary that becomes primary while hovered or dragging.
   Default width 150, hit height 20. */
export function Slider({value=0,min=0,max=1,step=0,width=150,disabled=false,showValue=false,onChange,style,...rest}){
  const ratio=max>min?(value-min)/(max-min):0;
  return <span style={{display:'inline-flex',alignItems:'center',gap:'var(--ui-gap)',...style}} {...rest}>
    <span style={{position:'relative',width:width+'px',height:'var(--size-slider-h)',display:'block'}}>
      <span aria-hidden="true" style={{position:'absolute',left:0,right:0,top:'50%',height:'2px',marginTop:'-1px',background:'var(--edge-strong)'}} />
      <span aria-hidden="true" style={{
        position:'absolute',left:`calc(${ratio*100}% - 8px)`,top:'50%',marginTop:'-8px',
        width:'var(--size-slider-knob)',height:'var(--size-slider-knob)',borderRadius:'var(--radius-pill)',
        background:disabled?'var(--action-disabled)':'var(--action-secondary)',
        border:'1px solid var(--edge-strong)',transition:'background var(--dur-fast) var(--ease-out-quad)',
      }} />
      <input type="range" value={value} min={min} max={max} step={step||'any'} disabled={disabled}
        onChange={e=>onChange&&onChange(parseFloat(e.target.value))}
        style={{position:'absolute',inset:0,width:'100%',height:'100%',opacity:0,margin:0,cursor:disabled?'not-allowed':'pointer'}} />
    <\/span>
    {showValue&&<span style={{fontFamily:'var(--font-mono)',fontSize:'12px',color:'var(--text-muted)',minWidth:'3ch'}}>{typeof value==='number'?value.toFixed(2):value}<\/span>}
  <\/span>;
}
