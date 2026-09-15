const { Panel, Label, Button, Checkbox, ProgressBar } = window.PyguaraDesignSystem_ca79d7;

/* pyguara/tools/performance.py — a 150x60 rect at (10,10), black fill,
   2px green border, "FPS: n" at 20px; the text turns red below 30 fps. */
function PerformanceMonitor({fps=60}){
  const c=fps<30?'var(--dbg-fps-bad)':'var(--dbg-fps-ok)';
  return <div style={{position:'absolute',left:10,top:10,width:150,height:60,background:'#000',border:'2px solid '+c,padding:'10px',boxSizing:'border-box',zIndex:15}}>
    <div style={{fontFamily:'var(--font-pixel)',fontSize:20,color:c,letterSpacing:'var(--ls-pixel)'}}>FPS: {fps}<\/div>
  <\/div>;
}

/* pyguara/tools/shortcuts_panel.py — 400x300 centred, rgba(10,10,20,240) fill,
   2px white border, yellow 24px heading, green keys, white descriptions. */
function ShortcutsPanel({onClose}){
  return <div style={{position:'absolute',left:'50%',top:'50%',transform:'translate(-50%,-50%)',width:400,background:'rgba(10,10,20,.941)',border:'2px solid #fff',padding:'30px 40px',boxSizing:'border-box',zIndex:30}}>
    <div style={{fontFamily:'var(--font-pixel)',fontSize:20,color:'#ff0',letterSpacing:'var(--ls-pixel)'}}>Developer Tools<\/div>
    <table style={{marginTop:16,borderCollapse:'collapse',fontFamily:'var(--font-pixel)',fontSize:13}}>
      <tbody>{window.EditorData.shortcuts.map(([k,d])=><tr key={k}>
        <td style={{color:'#64ff64',padding:'3px 26px 3px 0'}}>{k}<\/td><td style={{color:'#fff'}}>{d}<\/td><\/tr>)}<\/tbody>
    <\/table>
    <button type="button" onClick={onClose} style={{marginTop:18,background:'none',border:0,padding:0,color:'#969696',fontFamily:'var(--font-pixel)',fontSize:11,cursor:'pointer'}}>Press F8 to Close<\/button>
  <\/div>;
}

/* pyguara/tools/event_monitor.py — the engine is event-driven; this is the bus tap. */
function EventMonitor({onClose}){
  return <Panel borderWidth={2} padding="0" style={{position:'absolute',left:10,bottom:10,width:360,zIndex:16,boxShadow:'var(--shadow-stamp)'}}>
    <div style={{...window.panelTitle}}><span>Event Monitor<\/span>
      <button type="button" onClick={onClose} style={{background:'none',border:0,color:'var(--text-muted)',cursor:'pointer',fontFamily:'var(--font-mono)',fontSize:13}}>×<\/button><\/div>
    <div style={{padding:'6px 8px',maxHeight:150,overflow:'auto',display:'flex',flexDirection:'column',gap:2}}>
      {window.EditorData.events.map(([t,n,d],i)=><div key={i} style={{display:'grid',gridTemplateColumns:'46px 1fr',gap:6,fontFamily:'var(--font-mono)',fontSize:11}}>
        <span style={{color:'var(--text-faint)'}}>{t}<\/span>
        <span><span style={{color:'var(--accent-cool)'}}>{n}<\/span> <span style={{color:'var(--text-muted)'}}>{d}<\/span><\/span>
      <\/div>)}
    <\/div>
  <\/Panel>;
}

function PhysicsLegend(){
  const items=[['var(--dbg-collider-active)','collider active'],['var(--dbg-collider-sleeping)','sleeping'],['var(--dbg-collider-contact)','contact'],['var(--dbg-raycast)','raycast'],['var(--dbg-pathfinding)','pathfinding']];
  return <div style={{position:'absolute',right:10,top:10,background:'rgba(0,0,0,.72)',border:'1px solid var(--edge)',padding:'7px 9px',zIndex:15,display:'flex',flexDirection:'column',gap:3}}>
    {items.map(([c,l])=><div key={l} style={{display:'flex',gap:6,alignItems:'center',fontFamily:'var(--font-mono)',fontSize:10,color:'#fff'}}>
      <span style={{width:12,height:8,background:c,display:'block',outline:'1px solid rgba(255,255,255,.25)'}} />{l}<\/div>)}
  <\/div>;
}
Object.assign(window,{PerformanceMonitor,ShortcutsPanel,EventMonitor,PhysicsLegend});