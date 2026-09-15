import React from 'react';

/* Mirrors pyguara/ui/components/navbar.py — a Panel background plus a
   horizontal BoxContainer. Source: height 50, spacing 10, alignment START. */
export function NavBar({height=50,spacing=10,align='START',brand,children,style,...rest}){
  const justify={START:'flex-start',CENTER:'center',END:'flex-end',STRETCH:'space-between'}[align]||'flex-start';
  return <nav style={{
    display:'flex',alignItems:'center',justifyContent:justify,
    gap:spacing+'px',height:height+'px',padding:'0 var(--space-5)',
    background:'var(--surface-card)',
    borderBottom:'1px solid var(--edge-strong)',
    fontFamily:'var(--font-pixel)',color:'var(--text-body)',
    ...style,
  }} {...rest}>
    {brand&&<span style={{display:'flex',alignItems:'center',gap:'var(--ui-gap)',marginRight:'var(--space-5)'}}>{brand}<\/span>}
    {children}
  <\/nav>;
}
