import React,{useState} from 'react';

/* Mirrors pyguara/ui/components/button.py.
   Source behaviour, exactly: fill = theme.colors.primary; HOVERED and PRESSED
   both fill with theme.colors.secondary; DISABLED fills with
   theme.colors.background; a 2px border is always drawn, switching to
   secondary on FOCUSED; the 16px label is centred. Default size 120x40. */
const SKINS={
  primary:{bg:'var(--action-primary)',hover:'var(--action-secondary)',press:'var(--action-secondary-press)',fg:'var(--text-on-primary)',edge:'var(--edge-strong)'},
  secondary:{bg:'var(--action-secondary)',hover:'var(--action-secondary-hover)',press:'var(--action-secondary-press)',fg:'var(--text-on-secondary)',edge:'var(--edge-strong)'},
  wood:{bg:'var(--wood-500)',hover:'var(--wood-400)',press:'var(--wood-700)',fg:'var(--sand-100)',edge:'var(--rock-600)'},
  sage:{bg:'var(--colonial-500)',hover:'var(--colonial-400)',press:'var(--colonial-700)',fg:'var(--sage-100)',edge:'var(--colonial-700)'},
  ghost:{bg:'transparent',hover:'var(--action-ghost-hover)',press:'var(--theme-press-overlay)',fg:'var(--text-body)',edge:'var(--edge)'},
};
const SIZES={small:{h:30,px:10,fs:12},normal:{h:40,px:16,fs:16},large:{h:52,px:24,fs:24}};

export function Button({text,children,variant='primary',size='normal',disabled=false,focused=false,fullWidth=false,bevel=true,onClick,style,...rest}){
  const [hover,setHover]=useState(false);const [press,setPress]=useState(false);
  const s=SKINS[variant]||SKINS.primary;const z=SIZES[size]||SIZES.normal;
  const bg=disabled?'var(--action-disabled)':press?s.press:hover?s.hover:s.bg;
  return <button type="button" disabled={disabled} onClick={onClick}
    onMouseEnter={()=>setHover(true)} onMouseLeave={()=>{setHover(false);setPress(false)}}
    onMouseDown={()=>setPress(true)} onMouseUp={()=>setPress(false)}
    style={{
      minWidth:fullWidth?'100%':'var(--size-button-w)',
      height:z.h+'px',padding:`0 ${z.px}px`,
      display:'inline-flex',alignItems:'center',justifyContent:'center',gap:'var(--ui-gap)',
      background:bg,
      color:disabled?'var(--text-on-disabled)':s.fg,
      border:`2px solid ${focused?'var(--action-secondary)':s.edge}`,
      borderRadius:'var(--radius-0)',
      fontFamily:'var(--font-pixel)',fontSize:z.fs+'px',letterSpacing:'var(--ls-pixel)',
      textTransform:'uppercase',
      boxShadow:disabled||!bevel?'none':press?'var(--shadow-inset-bottom)':'var(--shadow-bevel)',
      transform:press&&!disabled?'translateY(1px)':'none',
      cursor:disabled?'not-allowed':'pointer',
      transition:'background var(--dur-fast) var(--ease-out-quad)',
      ...style,
    }} {...rest}>{children||text}<\/button>;
}
