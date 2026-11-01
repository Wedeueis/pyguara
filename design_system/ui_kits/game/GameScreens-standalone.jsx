const { Panel, Label, Button, Checkbox, Slider, ProgressBar, Image: DSImage, BoxContainer, Canvas: DSCanvas } = window.PyguaraDesignSystem_ca79d7;
const A='../../assets/'; /* standalone copy: image srcs come from window.__resources (see index-standalone.html meta tags) */

/* Every game screen is a WINDOW onto the one key-art illustration — never a
   recomposited plate. `scene-window-grove.png` is a 16:9 crop cut straight
   from it — grove, plank platform, water, Guará running, and no wordmark, so
   the transparent lockup can be overlaid on the title screen without
   duplicating a sign. (`scene-window-sign.png` is the complementary crop for
   surfaces that want the carved lockup baked in.) Aspect-matched crops, not
   object-position — the source aspect is too close to 16:9 to pan. */
function World({children,dim=0}){
  return <div style={{position:'relative',width:'100%',height:'100%',overflow:'hidden',background:'var(--sky-500)'}}>
    <img src={window.__resources.sceneGrove} alt="" style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover'}} />
    {dim>0&&<div style={{position:'absolute',inset:0,background:'var(--surface-scrim)',opacity:dim}} />}
    <div style={{position:'absolute',inset:0}}>{children}<\/div>
  <\/div>;
}

function TitleScreen({onPlay,onOptions}){
  return <World dim={.5}>
    <div style={{height:'100%',display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:18,padding:'20px 0',boxSizing:'border-box'}}>
      <img src={window.__resources.logoLockup} alt="Pyguara Solar Engine — Guará &amp; Falcão" style={{maxHeight:'36%',maxWidth:'62%',width:'auto',height:'auto',minHeight:0,flex:'0 1 auto',objectFit:'contain'}} />
      <BoxContainer direction="VERTICAL" align="CENTER" spacing={12}>
        <Button text="Play" variant="sage" size="large" onClick={onPlay} style={{minWidth:230}} />
        <Button text="Options" variant="wood" size="large" onClick={onOptions} style={{minWidth:230}} />
        <Button text="Quit" variant="wood" size="large" style={{minWidth:230}} />
      <\/BoxContainer>
      <Panel borderWidth={1} padding="7px 11px" style={{background:'var(--surface-card)',marginTop:2,whiteSpace:'nowrap',flex:'0 0 auto'}}>
        <Label text="Built on Pyguara" fontSize={12} color="var(--text-body)" />
      <\/Panel>
    <\/div>
  <\/World>;
}

/* HUD: health and stamina meters, fruit counter, falcão charges, all engine primitives. */
function Hud({fruit,health,stamina,charges}){
  return <>
    <div style={{position:'absolute',left:20,top:18,display:'flex',flexDirection:'column',gap:7}}>
      <Panel borderWidth={2} padding="8px 10px" bevel style={{background:'var(--surface-card)'}}>
        <div style={{display:'flex',alignItems:'center',gap:9}}>
          <img src={window.__resources.avatarGuara} alt="" style={{height:32,width:'auto'}} />
          <div style={{display:'flex',flexDirection:'column',gap:5}}>
            <ProgressBar value={health} width={168} height={14} fillColor="var(--state-danger)" />
            <ProgressBar value={stamina} width={168} height={9} fillColor="var(--state-warn)" />
          <\/div>
        <\/div>
      <\/Panel>
      <Panel borderWidth={2} padding="6px 10px" style={{background:'var(--surface-card)'}}>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <img src={window.__resources.avatarFalcao} alt="" style={{height:26,width:'auto'}} />
          <div style={{display:'flex',gap:4}}>{[0,1,2].map(i=><span key={i} style={{width:11,height:11,background:i<charges?'var(--falcao-400)':'transparent',border:'1px solid var(--falcao-400)',display:'block'}} />)}<\/div>
        <\/div>
      <\/Panel>
    <\/div>
    <Panel borderWidth={2} padding="7px 12px" bevel style={{position:'absolute',right:20,top:18,background:'var(--surface-card)'}}>
      <div style={{display:'flex',alignItems:'center',gap:9}}>
        <span style={{width:20,height:20,borderRadius:'50%',background:'var(--gold-500)',border:'2px solid var(--terra-500)',display:'block'}} />
        <Label text={String(fruit).padStart(2,'0')+' / 24'} font="pixel" fontSize={16} color="var(--sand-100)" />
      <\/div>
    <\/Panel>
    <div style={{position:'absolute',left:'50%',bottom:16,transform:'translateX(-50%)'}}>
      <img src={window.__resources.keycaps} alt="Move, jump and call Falcão" style={{height:44,imageRendering:'pixelated',opacity:.9}} />
    <\/div>
  <\/>;
}

function PlayScreen({onPause,fruit,onCollect}){
  return <World>
    <Hud fruit={fruit} health={.72} stamina={.45} charges={2} />
    <button type="button" onClick={onCollect} title="Collect the hanging fruit" style={{position:'absolute',left:'32.5%',top:'22%',width:34,height:34,borderRadius:'50%',background:'transparent',border:'2px solid var(--ink-900)',cursor:'pointer',boxShadow:'inset 0 0 0 2px var(--sand-100), 0 0 0 2px var(--sand-100), 0 0 0 5px rgba(30,18,12,.45)'}} />
    <Button text="Pause" variant="ghost" size="small" onClick={onPause} style={{position:'absolute',right:20,bottom:18,background:'var(--surface-overlay)'}} />
  <\/World>;
}

function PauseScreen({onResume,onOptions,onTitle}){
  return <World dim={.62}>
    <div style={{height:'100%',display:'grid',placeItems:'center'}}>
      <Panel borderWidth={3} padding="26px 30px" bevel style={{minWidth:330,boxShadow:'var(--shadow-stamp-lg)'}}>
        <Label text="PAUSED" font="display" fontSize={22} color="var(--action-secondary)" style={{textAlign:'center'}} />
        <BoxContainer direction="VERTICAL" align="CENTER" spacing={10} style={{marginTop:22}}>
          <Button text="Resume" variant="sage" onClick={onResume} style={{minWidth:220}} />
          <Button text="Options" variant="wood" onClick={onOptions} style={{minWidth:220}} />
          <Button text="Quit to Title" variant="wood" onClick={onTitle} style={{minWidth:220}} />
        <\/BoxContainer>
      <\/Panel>
    <\/div>
  <\/World>;
}

function OptionsScreen({onBack}){
  const [master,setMaster]=React.useState(.8),[music,setMusic]=React.useState(.55),[sfx,setSfx]=React.useState(.7);
  const [full,setFull]=React.useState(true),[vsync,setVsync]=React.useState(true),[shake,setShake]=React.useState(false),[colliders,setColliders]=React.useState(false);
  const Row=({label,children})=><div style={{display:'grid',gridTemplateColumns:'132px 1fr',alignItems:'center',gap:14,padding:'7px 0',borderBottom:'1px solid var(--edge-subtle)'}}>
    <Label text={label} fontSize={12} color="var(--text-muted)" />{children}<\/div>;
  return <World dim={.7}>
    <div style={{height:'100%',display:'grid',placeItems:'center',padding:20,boxSizing:'border-box'}}>
      <Panel borderWidth={3} padding="24px 28px" bevel style={{width:'min(520px,94%)',boxShadow:'var(--shadow-stamp-lg)'}}>
        <Label text="OPTIONS" font="display" fontSize={18} color="var(--action-secondary)" />
        <div style={{marginTop:16}}>
          <Label text="Audio" font="pixel" fontSize={14} color="var(--text-heading)" />
          <Row label="Master"><Slider value={master} onChange={setMaster} width={200} showValue /><\/Row>
          <Row label="Music"><Slider value={music} onChange={setMusic} width={200} showValue /><\/Row>
          <Row label="Effects"><Slider value={sfx} onChange={setSfx} width={200} showValue /><\/Row>
          <Label text="Display" font="pixel" fontSize={14} color="var(--text-heading)" style={{marginTop:16}} />
          <Row label="Fullscreen"><Checkbox label={full?'On':'Off'} checked={full} onChange={setFull} /><\/Row>
          <Row label="V-Sync"><Checkbox label={vsync?'On':'Off'} checked={vsync} onChange={setVsync} /><\/Row>
          <Row label="Screen shake"><Checkbox label={shake?'On':'Off'} checked={shake} onChange={setShake} /><\/Row>
          <Label text="Developer" font="pixel" fontSize={14} color="var(--text-heading)" style={{marginTop:16}} />
          <Row label="Show colliders"><Checkbox label={colliders?'On':'Off'} checked={colliders} onChange={setColliders} /><\/Row>
        <\/div>
        <div style={{display:'flex',gap:10,marginTop:20}}>
          <Button text="Back" variant="sage" onClick={onBack} />
          <Button text="Defaults" variant="ghost" />
        <\/div>
      <\/Panel>
    <\/div>
  <\/World>;
}

function GameApp(){
  const [screen,setScreen]=React.useState('title');
  const [fruit,setFruit]=React.useState(7);
  const [prev,setPrev]=React.useState('title');
  const go=s=>{setPrev(screen);setScreen(s);};
  return <div data-theme="game" style={{width:'100%',height:'100vh',background:'var(--ink-900)'}}>
    {screen==='title'&&<TitleScreen onPlay={()=>go('play')} onOptions={()=>go('options')} />}
    {screen==='play'&&<PlayScreen onPause={()=>go('pause')} fruit={fruit} onCollect={()=>setFruit(n=>Math.min(24,n+1))} />}
    {screen==='pause'&&<PauseScreen onResume={()=>go('play')} onOptions={()=>go('options')} onTitle={()=>go('title')} />}
    {screen==='options'&&<OptionsScreen onBack={()=>go(prev==='options'?'title':prev)} />}
  <\/div>;
}
Object.assign(window,{GameApp,TitleScreen,PlayScreen,PauseScreen,OptionsScreen,Hud,World});