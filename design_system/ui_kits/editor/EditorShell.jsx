const { Panel, Label, Button, Checkbox, Slider, Canvas: DSCanvas, NavBar, Image: DSImage, ProgressBar } = window.PyguaraDesignSystem_ca79d7;

function MenuBar({theme,onTheme,menu,onMenu,tools,toggleTool}){
  const items={File:[['Save Scene','Ctrl+S'],['Load Scene','Ctrl+L']],View:[['Hierarchy',null],['Inspector',null],['Assets',null]],Tools:window.EditorData.shortcuts.map(([k,d])=>[d,k])};
  return <div style={{position:'relative',zIndex:40}}>
    <NavBar height={34} spacing={2} align="STRETCH" style={{padding:'0 10px'}}
      brand={<DSImage src="../../assets/art/badge-pyguara-mark.png" height={24} alt="Pyguara Engine" />}>
      <div style={{display:'flex',gap:2,alignItems:'center',marginRight:'auto'}}>
        {Object.keys(items).map(m=><button key={m} type="button" onClick={()=>onMenu(menu===m?null:m)} style={{
          background:menu===m?'var(--theme-hover-overlay)':'transparent',border:0,padding:'5px 9px',
          color:'var(--text-body)',fontFamily:'var(--font-pixel)',fontSize:12,letterSpacing:'var(--ls-pixel)',cursor:'pointer'}}>{m}<\/button>)}
      <\/div>
      <div style={{display:'flex',gap:10,alignItems:'center'}}>
        <span style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)'}}>scene_roca_01<\/span>
        <Button text={theme==='light'?'Dusk':'Day'} variant="ghost" size="small" onClick={onTheme} style={{fontSize:11,minWidth:56}} />
      <\/div>
    <\/NavBar>
    {menu&&<div style={{position:'absolute',top:34,left:menu==='File'?44:menu==='View'?86:132,background:'var(--surface-raised)',border:'1px solid var(--edge-strong)',boxShadow:'var(--shadow-stamp)',minWidth:210,padding:4}}>
      {items[menu].map(([label,hint])=>{
        const isTool=menu==='Tools';const on=isTool&&tools[label];
        return <button key={label} type="button" onClick={()=>{isTool&&toggleTool(label);onMenu(null);}} style={{
          width:'100%',display:'flex',justifyContent:'space-between',gap:16,padding:'6px 8px',background:'none',border:0,
          color:'var(--text-body)',fontFamily:'var(--font-pixel)',fontSize:12,cursor:'pointer',textAlign:'left'}}>
          <span>{isTool?(on?'\u2713 ':'\u00a0\u00a0\u00a0')+label:label}<\/span>
          {hint&&<span style={{color:'var(--text-faint)',fontFamily:'var(--font-mono)',fontSize:11}}>{hint}<\/span>}
        <\/button>;})}
    <\/div>}
  <\/div>;
}

function Viewport({tools,gizmos,onGizmos,zoom,onZoom}){
  return <section style={{gridArea:'view',position:'relative',background:'var(--surface-inset)',border:'1px solid var(--edge-strong)',display:'flex',flexDirection:'column',minHeight:0}}>
    <header style={{...window.panelTitle}}>
      <span>Scene — roca_01<\/span>
      <span style={{display:'flex',gap:12,alignItems:'center'}}>
        <Checkbox label="Gizmos" checked={gizmos} onChange={onGizmos} style={{fontSize:11}} />
        <span style={{display:'flex',gap:6,alignItems:'center',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)'}}>zoom
          <Slider value={zoom} min={1} max={4} step={0.5} width={70} onChange={onZoom} /><span style={{color:'var(--text-muted)',minWidth:26}}>{zoom.toFixed(1)}×<\/span><\/span>
      <\/span>
    <\/header>
    <div style={{flex:1,position:'relative',overflow:'hidden',minHeight:0}}>
      <img src="../../assets/art/scene-window-grove.png" alt="Cerrado scene" style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover'}} />
      <div style={{position:'absolute',inset:0,backgroundImage:'linear-gradient(to right,rgba(0,0,0,.14) 1px,transparent 1px),linear-gradient(to bottom,rgba(0,0,0,.14) 1px,transparent 1px)',backgroundSize:'32px 32px'}} />
      {gizmos&&<>
        <div style={{position:'absolute',left:'26%',top:'46%',width:56,height:80,border:'2px solid rgba(0,255,0,.588)'}}>
          <span style={{position:'absolute',top:-16,left:0,fontFamily:'var(--font-mono)',fontSize:10,color:'#0f0'}}>guara_player<\/span><\/div>
        <div style={{position:'absolute',left:'54%',top:'62%',width:128,height:32,border:'2px solid rgba(128,128,128,.588)'}} />
        <div style={{position:'absolute',left:'72%',top:'58%',width:40,height:40,border:'2px solid rgba(255,0,0,.706)',borderRadius:'50%'}} />
        <div style={{position:'absolute',left:'30%',top:'52%',width:180,height:2,background:'var(--dbg-raycast)',transformOrigin:'left',transform:'rotate(-9deg)'}} />
      <\/>}
      {tools['Performance Monitor']&&<window.PerformanceMonitor fps={60} />}
      {tools['Physics Debugger']&&<window.PhysicsLegend />}
      {tools['Event Monitor']&&<window.EventMonitor onClose={()=>{}} />}
    <\/div>
    <footer style={{flex:'0 0 auto',height:24,display:'flex',alignItems:'center',gap:16,padding:'0 8px',borderTop:'1px solid var(--edge)',background:'var(--surface-card)',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)'}}>
      <span>7 entities<\/span><span>ECS · 14 systems<\/span><span>pymunk 6.6<\/span><span style={{marginLeft:'auto'}}>F12 toggles all tools<\/span>
    <\/footer>
  <\/section>;
}

function EditorApp(){
  const D=window.EditorData;
  const [theme,setTheme]=React.useState('dark');
  const [sel,setSel]=React.useState(D.entities[0].id);
  const [filter,setFilter]=React.useState('');
  const [menu,setMenu]=React.useState(null);
  const [res,setRes]=React.useState(null);
  const [gizmos,setGizmos]=React.useState(true);
  const [zoom,setZoom]=React.useState(2);
  const [tools,setTools]=React.useState({'Performance Monitor':true,'Physics Debugger':true,'Event Monitor':false,'Shortcuts Panel (This)':false});
  const toggleTool=n=>setTools(t=>({...t,[n]:!t[n]}));
  React.useEffect(()=>{const h=e=>{
    const map={F1:'Performance Monitor',F2:'Entity Inspector',F3:'Event Monitor',F4:'Physics Debugger',F8:'Shortcuts Panel (This)'};
    if(map[e.key]){e.preventDefault();toggleTool(map[e.key]);}
    if(e.key==='F12'){e.preventDefault();setTools(t=>{const any=Object.values(t).some(Boolean);const o={};for(const k in t)o[k]=!any;return o;});}
  };window.addEventListener('keydown',h);return()=>window.removeEventListener('keydown',h);},[]);
  const entity=D.entities.find(e=>e.id===sel);
  return <div data-theme={theme==='light'?'light':undefined} style={{height:'100vh',display:'flex',flexDirection:'column',background:'var(--surface-page)',color:'var(--text-body)',overflow:'hidden'}}>
    <MenuBar theme={theme} onTheme={()=>setTheme(t=>t==='light'?'dark':'light')} menu={menu} onMenu={setMenu} tools={tools} toggleTool={toggleTool} />
    <div style={{flex:1,minHeight:0,position:'relative',display:'grid',gridTemplateColumns:'232px minmax(0,1fr) 268px',gridTemplateRows:'minmax(0,1fr) 176px',gridTemplateAreas:'"left view right" "assets assets right"',gap:6,padding:6}}>
      <window.HierarchyPanel entities={D.entities} selected={sel} onSelect={setSel} filter={filter} onFilter={setFilter} />
      <Viewport tools={tools} gizmos={gizmos} onGizmos={setGizmos} zoom={zoom} onZoom={setZoom} />
      <window.InspectorPanel entity={entity} />
      <window.AssetsPanel selected={res} onSelect={setRes} />
      <window.ResourceInspector path={res} onClose={()=>setRes(null)} />
      {tools['Shortcuts Panel (This)']&&<window.ShortcutsPanel onClose={()=>toggleTool('Shortcuts Panel (This)')} />}
    <\/div>
  <\/div>;
}
Object.assign(window,{EditorApp,MenuBar,Viewport});