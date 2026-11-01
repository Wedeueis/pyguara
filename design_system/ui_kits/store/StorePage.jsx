const { Panel, Label, Button, NavBar, Image: DSImage, ProgressBar, Checkbox } = window.PyguaraDesignSystem_ca79d7;
const A='../../assets/';
const SHOTS=[A+'art/scene-cerrado-solar.png',A+'art/tiles-plank-platform.png',A+'art/props-trees.png',A+'art/prop-solar-leaf-panel.png'];

function StoreApp(){
  const [shot,setShot]=React.useState(0);
  const [follow,setFollow]=React.useState(false);
  const [tip,setTip]=React.useState('5');
  return <div style={{maxWidth:1000,margin:'0 auto',padding:'0 20px 80px'}}>
    <NavBar height={54} align="STRETCH" style={{padding:'0 4px',background:'transparent',borderBottom:'1px solid var(--edge)'}}
      brand={<Label text="GUARÁ & FALCÃO" font="display" fontSize={12} color="var(--text-heading)" />}>
      <div style={{display:'flex',gap:8}}>
        <Button text={follow?'Following':'Follow'} variant="ghost" size="small" onClick={()=>setFollow(v=>!v)} />
        <Button text="Share" variant="ghost" size="small" />
      <\/div>
    <\/NavBar>

    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:26,marginTop:26,alignItems:'start'}}>
      <div style={{minWidth:0}}>
        <Panel borderWidth={2} padding="0" style={{overflow:'hidden'}}>
          <img src={SHOTS[shot]} alt="Screenshot" style={{display:'block',width:'100%',height:300,objectFit:'cover'}} />
        <\/Panel>
        <div style={{display:'flex',gap:8,marginTop:8,overflowX:'auto',paddingBottom:4}}>
          {SHOTS.map((s,i)=><button key={s} type="button" onClick={()=>setShot(i)} style={{
            flex:'0 0 auto',padding:0,width:96,height:60,overflow:'hidden',cursor:'pointer',
            border:'2px solid '+(i===shot?'var(--action-secondary)':'var(--edge)'),background:'var(--surface-inset)'}}>
            <img src={s} alt="" style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}} /><\/button>)}
        <\/div>

        <h1 style={{margin:'28px 0 0',fontFamily:'var(--font-pixel)',fontSize:'clamp(22px,3.6vw,30px)',letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)'}}>Guará &amp; Falcão<\/h1>
        <p style={{margin:'6px 0 0',fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-faint)'}}>A platformer adventure · by Wedeueis · devlog 14<\/p>
        <p style={{fontSize:17,lineHeight:'var(--lh-body)',color:'var(--text-body)',maxWidth:'64ch',marginTop:22,textWrap:'pretty'}}>
          A maned wolf runs the Brazilian Cerrado at dusk. A falcon rides on his back and spends himself
          three times before he has to land. Beneath the tableland, old machinery is still turning — greened over and kept
          running, and the platforms you need are the parts still in motion.
        <\/p>
        <p style={{fontSize:17,lineHeight:'var(--lh-body)',color:'var(--text-muted)',maxWidth:'64ch',textWrap:'pretty'}}>
          Momentum is the whole puzzle. Guará cannot double-jump. Falcão can carry you across one gap,
          not two. Stalling a gear changes the level's shape, and you have to want that.
        <\/p>

        <h2 style={{marginTop:34,fontFamily:'var(--font-pixel)',fontSize:17,letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)'}}>Features<\/h2>
        <ul style={{margin:'12px 0 0',padding:0,listStyle:'none',display:'grid',gap:8}}>
          {['Hand-animated pixel art at 12 fps — every frame drawn, none tweened',
            'One biome, studied properly: the Cerrado in three seasons',
            'Machinery you can stall, reverse or ride',
            'Open-source engine — the editor ships with the game'].map(t=>
            <li key={t} style={{display:'flex',gap:10,fontSize:16,lineHeight:'var(--lh-body)',color:'var(--text-muted)'}}>
              <span style={{color:'var(--action-secondary)',flex:'0 0 auto'}}>▪<\/span>{t}<\/li>)}
        <\/ul>
      <\/div>

      <aside style={{minWidth:0,display:'flex',flexDirection:'column',gap:16,position:'sticky',top:16}}>
        <Panel borderWidth={2} padding="18px">
          <Label text="Name your own price" fontSize={12} color="var(--text-muted)" />
          <div style={{display:'flex',alignItems:'baseline',gap:6,marginTop:8}}>
            <span style={{fontFamily:'var(--font-pixel)',fontSize:26,color:'var(--text-heading)'}}>$12<\/span>
            <span style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-faint)'}}>suggested<\/span>
          <\/div>
          <div style={{display:'flex',gap:6,marginTop:14}}>
            {['5','12','25'].map(v=><Button key={v} text={'$'+v} size="small" variant={tip===v?'primary':'ghost'} onClick={()=>setTip(v)} style={{minWidth:52}} />)}
          <\/div>
          <Button text="Buy now" variant="sage" size="large" fullWidth style={{marginTop:14}} />
          <Button text="Download demo" variant="wood" fullWidth style={{marginTop:8}} />
          <div style={{marginTop:14,fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',lineHeight:1.7}}>
            Windows · macOS · Linux<br/>1.4 GB · DRM-free
          <\/div>
        <\/Panel>

        <Panel padding="16px">
          <Label text="Development" fontSize={12} color="var(--text-muted)" />
          <div style={{marginTop:12,display:'flex',flexDirection:'column',gap:10}}>
            {[['Chapter 1',1],['Chapter 2',.55],['Chapter 3',.1]].map(([t,v])=><div key={t}>
              <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',marginBottom:4}}>{t}<\/div>
              <ProgressBar value={v} width={0} style={{width:'100%'}} /><\/div>)}
          <\/div>
        <\/Panel>

        <Panel padding="16px">
          <Label text="Details" fontSize={12} color="var(--text-muted)" />
          <table style={{width:'100%',borderCollapse:'collapse',marginTop:10,fontFamily:'var(--font-mono)',fontSize:12}}>
            <tbody>{[['Status','In development'],['Genre','Platformer'],['Engine','Pyguara'],['Tags','pixel-art, cerrado'],['Languages','pt-BR, en'],['Input','Keyboard, gamepad']]
              .map(([k,v])=><tr key={k}>
                <td style={{padding:'5px 0',color:'var(--text-faint)',verticalAlign:'top'}}>{k}<\/td>
                <td style={{padding:'5px 0 5px 12px',color:'var(--text-body)'}}>{v}<\/td><\/tr>)}<\/tbody>
          <\/table>
        <\/Panel>

        <Panel padding="16px">
          <div style={{display:'flex',alignItems:'center',gap:12}}>
            <img src={A+'art/badge-pyguara-mark.png'} alt="Pyguara Engine" style={{height:52}} />
            <div><Label text="Made with Pyguara" fontSize={12} color="var(--text-body)" />
              <div style={{marginTop:6}}><Button text="Get the engine" variant="ghost" size="small" style={{fontSize:11}} /><\/div><\/div>
          <\/div>
        <\/Panel>
      <\/aside>
    <\/div>
  <\/div>;
}
Object.assign(window,{StoreApp});