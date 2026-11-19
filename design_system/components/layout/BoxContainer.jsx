import React from 'react';

/* Mirrors pyguara/ui/layout.py BoxContainer — stacks children linearly.
   Source: direction VERTICAL by default, alignment START, spacing 5.
   Note the engine centres children on the CROSS axis unconditionally. */
export function BoxContainer({direction='VERTICAL',align='START',spacing=5,crossCenter=true,style,children,...rest}){
  const vertical=direction==='VERTICAL';
  const main={START:'flex-start',CENTER:'center',END:'flex-end',STRETCH:'space-between'}[align]||'flex-start';
  return <div style={{
    display:'flex',flexDirection:vertical?'column':'row',
    justifyContent:main,
    alignItems:crossCenter?'center':'stretch',
    gap:spacing+'px',...style,
  }} {...rest}>{children}<\/div>;
}
