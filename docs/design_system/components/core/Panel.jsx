import React from 'react';

/* Mirrors pyguara/ui/components/panel.py — a colored rectangle with a border.
   Source defaults: color = theme.colors.background, border_width = 1. */
export function Panel({color,borderWidth=1,padding='var(--ui-padding)',bevel=false,as:Tag='div',style,children,...rest}){
  const panelStyle={
    background:color||'var(--surface-card)',
    border:`${borderWidth}px solid var(--edge-strong)`,
    borderRadius:'var(--radius-0)',
    padding,
    boxShadow:bevel?'var(--shadow-bevel)':'none',
    color:'var(--text-body)',
    fontFamily:'var(--font-body)',
    ...style,
  };
  return <Tag style={panelStyle} {...rest}>{children}<\/Tag>;
}
