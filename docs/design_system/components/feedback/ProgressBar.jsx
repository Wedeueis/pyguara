import React from 'react';

/* Mirrors pyguara/ui/components/progress_bar.py. Source: background in
   theme.colors.background, a 1px border, and a left-anchored fill in
   theme.colors.secondary whose width is rect.width * value.
   Value is clamped 0.0-1.0. Default size 200x20. */
export function ProgressBar({value=0.5,width=200,height=20,fillColor,bgColor,label,style,...rest}){
  const v=Math.max(0,Math.min(1,value));
  return <span style={{display:'inline-flex',alignItems:'center',gap:'var(--ui-gap)',...style}} {...rest}>
    <span style={{
      position:'relative',display:'block',width:width+'px',height:height+'px',
      background:bgColor||'var(--surface-inset)',border:'1px solid var(--edge-strong)',
      overflow:'hidden',
    }}>
      <span style={{
        position:'absolute',left:0,top:0,bottom:0,width:(v*100)+'%',
        background:fillColor||'var(--action-secondary)',
        transition:'width var(--dur-normal) var(--ease-out-quad)',
      }} />
    <\/span>
    {label&&<span style={{fontFamily:'var(--font-mono)',fontSize:'12px',color:'var(--text-muted)'}}>{label}<\/span>}
  <\/span>;
}
