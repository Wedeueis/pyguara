const { Panel, Label, Button, NavBar, TextInput, Image: DSImage } = window.PyguaraDesignSystem_ca79d7;
const A='../../assets/';
/* Sidebar sections are the engine's real top-level packages. */
const NAV=[
 ['Getting started',['Install','Your first scene','Project layout']],
 ['ecs',['EntityManager','Component','Query cache','Events']],
 ['graphics',['Render pipeline','Spritesheet & Atlas','Animation system','Nine-patch','Lighting','VFX']],
 ['physics',['PhysicsSystem','Collider & RigidBody','PlatformerController','Trigger volumes','Joints']],
 ['ui',['UITheme','Theme presets','Components','Layout','Constraints']],
 ['ai',['Behavior tree','FSM','Steering','Pathfinding','Navmesh']],
 ['resources',['ResourceManager','Loaders','Meta files','Hot reload']],
 ['scene',['SceneManager','Serializer','Transitions']],
 ['tools',['Editor','Performance','Event monitor','Gizmos','Debugger']],
];
function DocsApp(){
  const [active,setActive]=React.useState('Theme presets');
  const [q,setQ]=React.useState('');
  return <div style={{minHeight:'100vh',display:'grid',gridTemplateColumns:'minmax(0,1fr)'}}>
    <NavBar height={58} align="STRETCH" style={{position:'sticky',top:0,zIndex:30,padding:'0 22px',borderBottom:'1px solid var(--edge-strong)'}}
      brand={<span style={{display:'flex',alignItems:'center',gap:10}}>
        <img src={A+'art/badge-pyguara-mark.png'} alt="Pyguara Engine" style={{height:34}} />
        <span style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',border:'1px solid var(--edge)',padding:'2px 6px'}}>0.9.0-dev<\/span>
      <\/span>}>
      <div style={{display:'flex',gap:10,alignItems:'center'}}>
        <TextInput value={q} onChange={setQ} placeholder="Search docs" mono width={200} style={{height:28,fontSize:12}} />
        <Button text="GitHub" variant="ghost" size="small" />
      <\/div>
    <\/NavBar>
    <div style={{display:'grid',gridTemplateColumns:'minmax(0,232px) minmax(0,1fr)',alignItems:'start'}}>
      <aside style={{position:'sticky',top:58,alignSelf:'start',maxHeight:'calc(100vh - 58px)',overflow:'auto',borderRight:'1px solid var(--edge)',padding:'22px 14px',background:'var(--surface-card)'}}>
        {NAV.map(([sec,items])=><div key={sec} style={{marginBottom:20}}>
          <div style={{fontFamily:'var(--font-mono)',fontSize:10,letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--action-secondary)',marginBottom:7}}>{sec}<\/div>
          <div style={{display:'flex',flexDirection:'column'}}>
            {items.map(it=><button key={it} type="button" onClick={()=>setActive(it)} style={{
              textAlign:'left',padding:'4px 8px',border:0,borderLeft:'2px solid '+(active===it?'var(--action-primary)':'transparent'),
              background:active===it?'var(--action-ghost-hover)':'transparent',
              color:active===it?'var(--text-heading)':'var(--text-muted)',
              fontFamily:'var(--font-body)',fontSize:14,cursor:'pointer'}}>{it}<\/button>)}
          <\/div>
        <\/div>)}
      <\/aside>
      <main style={{padding:'40px 32px 80px',maxWidth:820,minWidth:0}}>
        <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',marginBottom:12}}>ui / {active}<\/div>
        <h1 style={{margin:0,fontFamily:'var(--font-pixel)',fontSize:30,letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)'}}>Theme presets<\/h1>
        <p style={{fontSize:18,lineHeight:'var(--lh-body)',color:'var(--text-muted)',maxWidth:'66ch',textWrap:'pretty'}}>
          <code style={{fontFamily:'var(--font-mono)',fontSize:15}}>pyguara.ui.theme_presets<\/code> ships six
          ready-to-use themes. All are immutable — clone one and modify the copy.
        <\/p>
        <Panel padding="0" style={{marginTop:26,overflow:'hidden'}}>
          <div style={{padding:'7px 12px',borderBottom:'1px solid var(--edge)',background:'var(--surface-raised)',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',display:'flex',justifyContent:'space-between'}}>
            <span>python<\/span><span>theme_presets.py<\/span><\/div>
          <pre style={{margin:0,padding:'14px 16px',overflow:'auto',fontFamily:'var(--font-mono)',fontSize:14,lineHeight:1.65,color:'var(--text-body)'}}>
<span style={{color:'var(--accent-cool)'}}>from<\/span> pyguara.ui.theme_presets <span style={{color:'var(--accent-cool)'}}>import<\/span> Themes{'\n'}
<span style={{color:'var(--accent-cool)'}}>from<\/span> pyguara.ui.theme <span style={{color:'var(--accent-cool)'}}>import<\/span> set_theme{'\n\n'}
<span style={{color:'var(--text-faint)'}}># Use dark theme<\/span>{'\n'}
set_theme(Themes.DARK){'\n\n'}
<span style={{color:'var(--text-faint)'}}># Customize a preset<\/span>{'\n'}
my_theme = Themes.LIGHT.clone(){'\n'}
my_theme.colors.primary = Color(<span style={{color:'var(--state-warn)'}}>255<\/span>, <span style={{color:'var(--state-warn)'}}>0<\/span>, <span style={{color:'var(--state-warn)'}}>0<\/span>){'\n'}
set_theme(my_theme)<\/pre>
        <\/Panel>
        <h2 style={{marginTop:38,fontFamily:'var(--font-pixel)',fontSize:20,letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)'}}>Available presets<\/h2>
        <div style={{overflowX:'auto',marginTop:14}}>
          <table style={{width:'100%',minWidth:520,borderCollapse:'collapse',fontSize:14}}>
            <thead><tr>{['Name','primary','background','border width','radius'].map(h=><th key={h} style={{textAlign:'left',padding:'8px 10px',borderBottom:'2px solid var(--edge-strong)',fontFamily:'var(--font-mono)',fontSize:11,letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--text-faint)',fontWeight:400}}>{h}<\/th>)}<\/tr><\/thead>
            <tbody>{[['DARK','70, 130, 180','32, 32, 32','2','0'],['LIGHT','41, 128, 185','236, 240, 241','1','4'],['HIGH_CONTRAST','255, 255, 255','0, 0, 0','3','0'],['CYBERPUNK','255, 0, 255','10, 10, 20','2','0'],['FOREST','46, 125, 50','33, 43, 33','2','8'],['RETRO','255, 152, 0','66, 66, 66','3','0']]
              .map(r=><tr key={r[0]}>{r.map((c,i)=><td key={i} style={{padding:'8px 10px',borderBottom:'1px solid var(--edge-subtle)',fontFamily:i?'var(--font-mono)':'var(--font-pixel)',fontSize:i?13:12,color:i?'var(--text-muted)':'var(--text-body)'}}>{c}<\/td>)}<\/tr>)}<\/tbody>
          <\/table>
        <\/div>
        <Panel borderWidth={2} padding="14px 16px" style={{marginTop:30,background:'var(--surface-inset)'}}>
          <div style={{fontFamily:'var(--font-mono)',fontSize:11,letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--action-secondary)'}}>Note<\/div>
          <p style={{margin:'7px 0 0',fontSize:15,lineHeight:'var(--lh-body)',color:'var(--text-muted)'}}>
            Themes serialize to JSON with <code style={{fontFamily:'var(--font-mono)'}}>UITheme.to_json()<\/code> and load with
            <code style={{fontFamily:'var(--font-mono)'}}> UITheme.load(path)<\/code>, so a game can ship themes as resources.
          <\/p>
        <\/Panel>
        <nav style={{display:'flex',justifyContent:'space-between',gap:14,marginTop:40,paddingTop:20,borderTop:'1px solid var(--edge)'}}>
          <Button text="← UITheme" variant="ghost" size="small" /><Button text="Components →" variant="ghost" size="small" />
        <\/nav>
      <\/main>
    <\/div>
  <\/div>;
}
Object.assign(window,{DocsApp});