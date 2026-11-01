const { Panel, Label, Button, NavBar, Image: DSImage, ProgressBar, BoxContainer } = window.PyguaraDesignSystem_ca79d7;
const A='../../assets/';
const wrap={maxWidth:1080,margin:'0 auto',padding:'0 24px'};
const H2=({t,k})=><div style={{marginBottom:22}}>
  {k&&<div style={{fontFamily:'var(--font-mono)',fontSize:11,letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--action-secondary)',marginBottom:9}}>{k}<\/div>}
  <h2 style={{margin:0,fontFamily:'var(--font-pixel)',fontSize:'clamp(22px,3.4vw,32px)',letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)',textWrap:'pretty'}}>{t}<\/h2><\/div>;

function SiteApp(){
  const [wish,setWish]=React.useState(false);
  return <>
    <NavBar height={62} align="STRETCH" style={{position:'sticky',top:0,zIndex:30,padding:'0 24px',background:'var(--surface-overlay)',backdropFilter:'blur(6px)'}}
      brand={<img src={A+'art/logo-pyguara-lockup.png'} alt="Guará &amp; Falcão" style={{height:38}} />}>
      <div style={{display:'flex',gap:8,alignItems:'center'}}>
        <Button text="The World" variant="ghost" size="small" />
        <Button text="Engine" variant="ghost" size="small" />
        <Button text="Devlog" variant="ghost" size="small" />
        <Button text={wish?'Wishlisted':'Wishlist'} size="small" onClick={()=>setWish(w=>!w)} />
      <\/div>
    <\/NavBar>

    <header style={{position:'relative',overflow:'hidden',borderBottom:'2px solid var(--edge-strong)'}}>
      <img src={A+'art/scene-window-grove.png'} alt="" style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover'}} />
      <div style={{position:'absolute',inset:0,background:'linear-gradient(180deg,rgba(29,22,32,.5),rgba(29,22,32,.92))'}} />
      <div style={{...wrap,position:'relative',padding:'86px 24px 96px'}}>
        <div style={{maxWidth:600}}>
          <img src={A+'art/logo-pyguara-lockup.png'} alt="Pyguara Solar Engine — Guará &amp; Falcão" style={{width:'min(420px,100%)'}} />
          <p style={{fontSize:20,lineHeight:'var(--lh-body)',color:'var(--sand-100)',margin:'22px 0 0',textWrap:'pretty'}}>
            A maned wolf runs the Brazilian Cerrado. A falcon rides on his back. The platforms are
            solar, the water is piped, and someone keeps all of it running.
          <\/p>
          <div style={{display:'flex',flexWrap:'wrap',gap:12,marginTop:28}}>
            <Button text={wish?'On your wishlist':'Wishlist'} variant="sage" size="large" onClick={()=>setWish(w=>!w)} />
            <Button text="Watch the trailer" variant="wood" size="large" />
          <\/div>
          <div style={{display:'flex',gap:20,marginTop:24,fontFamily:'var(--font-mono)',fontSize:12,color:'var(--sand-200)'}}>
            <span>Windows · macOS · Linux<\/span><span>Single player<\/span><span>2027<\/span>
          <\/div>
        <\/div>
      <\/div>
    <\/header>

    <section style={{...wrap,padding:'72px 24px'}}>
      <H2 k="Two animals, one run" t="Guará runs. Falcão carries." />
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',gap:20}}>
        {[[A+'art/hero-guara.png','Guará','Heavy, fast, committed. He cannot double-jump — momentum is the whole puzzle.'],
          [A+'art/sprite-falcao.png','Falcão','Three charges. Spend one to hover, glide a gap, or scout what the camera will not show you.'],
          [A+'art/prop-solar-leaf-panel.png','The engine below','Every roça platform runs on solar leaf and piped water. Stall one and the level changes shape.']]
          .map(([src,t,d])=><Panel key={t} borderWidth={2} padding="0" style={{overflow:'hidden'}}>
            <div style={{height:148,display:'grid',placeItems:'center',background:'var(--surface-inset)',borderBottom:'1px solid var(--edge)'}}>
              <img src={src} alt="" style={{maxHeight:112,maxWidth:'80%'}} /><\/div>
            <div style={{padding:'16px 18px'}}>
              <Label text={t} font="pixel" fontSize={16} color="var(--text-heading)" />
              <p style={{margin:'9px 0 0',fontSize:15,lineHeight:'var(--lh-body)',color:'var(--text-muted)',textWrap:'pretty'}}>{d}<\/p><\/div>
          <\/Panel>)}
      <\/div>
    <\/section>

    <section style={{background:'var(--surface-card)',borderTop:'1px solid var(--edge)',borderBottom:'1px solid var(--edge)'}}>
      <div style={{...wrap,padding:'64px 24px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:36,alignItems:'center'}}>
        <div>
          <H2 k="Built in the open" t="Runs on Pyguara, our own engine" />
          <p style={{fontSize:17,lineHeight:'var(--lh-body)',color:'var(--text-muted)',margin:0,maxWidth:'52ch',textWrap:'pretty'}}>
            Pyguara is a data-driven, event-driven 2D engine on pygame and pymunk. Entities are
            component compositions; systems query them each frame. It ships an ECS, a physics layer,
            a scene serializer, hot reload, and an in-game editor. It is open source.
          <\/p>
          <div style={{display:'flex',gap:12,marginTop:24}}>
            <Button text="Read the docs" variant="secondary" />
            <Button text="Source on GitHub" variant="ghost" />
          <\/div>
        <\/div>
        <div style={{display:'grid',placeItems:'center'}}>
          <img src={A+'art/badge-pyguara-mark.png'} alt="Pyguara Engine" style={{width:'min(230px,70%)'}} />
        <\/div>
      <\/div>
    <\/section>

    <section style={{...wrap,padding:'72px 24px'}}>
      <H2 k="Progress" t="What is done" />
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:18}}>
        {[['Cerrado biome',1],['Guará moveset',.9],['Falcão flight',.65],['Roça machinery',.4],['Soundtrack',.25]]
          .map(([t,v])=><Panel key={t} padding="14px 16px">
            <Label text={t} fontSize={13} color="var(--text-body)" />
            <div style={{marginTop:10}}><ProgressBar value={v} width={0} style={{width:'100%'}} label={Math.round(v*100)+'%'} /><\/div>
          <\/Panel>)}
      <\/div>
    <\/section>

    <footer style={{borderTop:'2px solid var(--edge-strong)',background:'var(--surface-card)'}}>
      <div style={{...wrap,padding:'34px 24px',display:'flex',flexWrap:'wrap',gap:18,alignItems:'center',justifyContent:'space-between'}}>
        <img src={A+'art/badge-pyguara-mark.png'} alt="Pyguara Engine" style={{height:44}} />
        <div style={{display:'flex',gap:18,fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-muted)',flexWrap:'wrap'}}>
          <a href="#docs">Docs<\/a><a href="#press">Press kit<\/a><a href="#devlog">Devlog<\/a><a href="#contact">Contact<\/a>
        <\/div>
      <\/div>
    <\/footer>
  <\/>;
}
Object.assign(window,{SiteApp});