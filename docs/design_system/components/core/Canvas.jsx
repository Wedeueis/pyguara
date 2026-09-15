import React from 'react';

/* Mirrors pyguara/ui/components/canvas.py — a cleared drawing surface used
   for mini-maps, previews and graphs. Children do the actual drawing. */
export function Canvas({width,height,bgColor,grid=false,style,children,...rest}){
  return <div style={{
    position:'relative',
    width:width?width+'px':'100%',
    height:height?height+'px':'160px',
    background:bgColor||'var(--surface-inset)',
    border:'1px solid var(--edge)',
    overflow:'hidden',
    backgroundImage:grid?'linear-gradient(to right,var(--edge-subtle) 1px,transparent 1px),linear-gradient(to bottom,var(--edge-subtle) 1px,transparent 1px)':'none',
    backgroundSize:grid?'var(--size-tile) var(--size-tile)':'auto',
    ...style,
  }} {...rest}>{children}<\/div>;
}
