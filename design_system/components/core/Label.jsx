import React from 'react';

/* Mirrors pyguara/ui/components/text.py — read-only auto-sizing text.
   Source default font_size is 16 (the engine's size_normal). */
export function Label({text,fontSize=16,color,font='pixel',uppercase=false,anchor='TOP_LEFT',style,...rest}){
  const families={pixel:'var(--font-pixel)',display:'var(--font-display)',body:'var(--font-body)',mono:'var(--font-mono)'};
  const align=anchor.includes('CENTER')&&!anchor.startsWith('CENTER')?'center':anchor.includes('RIGHT')?'right':'left';
  return <span style={{
    display:'block',
    fontFamily:families[font],
    fontSize:fontSize+'px',
    lineHeight:'var(--lh-snug)',
    letterSpacing:font==='display'?'var(--ls-display)':'var(--ls-pixel)',
    color:color||'var(--text-body)',
    textTransform:uppercase?'uppercase':'none',
    textAlign:align,
    ...style,
  }} {...rest}>{text}<\/span>;
}
