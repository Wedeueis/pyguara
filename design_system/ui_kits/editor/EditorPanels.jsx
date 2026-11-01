const { Panel, Label, Button, Checkbox, Slider, TextInput, Canvas: DSCanvas, ProgressBar } = window.PyguaraDesignSystem_ca79d7;

const panelChrome={background:'var(--surface-card)',border:'1px solid var(--edge-strong)',display:'flex',flexDirection:'column',minHeight:0};
const panelTitle={height:26,flex:'0 0 auto',display:'flex',alignItems:'center',justifyContent:'space-between',padding:'0 8px',background:'var(--surface-raised)',borderBottom:'1px solid var(--edge)',fontFamily:'var(--font-pixel)',fontSize:12,letterSpacing:'var(--ls-pixel)',color:'var(--text-heading)'};
const panelBody={flex:1,overflow:'auto',padding:8,minHeight:0};

function EditorPanel({title,actions,children,style}){
  return <section style={{...panelChrome,...style}}>
    <header style={panelTitle}><span>{title}<\/span><span style={{display:'flex',gap:6}}>{actions}<\/span><\/header>
    <div style={panelBody}>{children}<\/div>
  <\/section>;
}

/* pyguara/editor/panels/hierarchy.py — label is "tag.name (id[:8])", or just id[:8] with no Tag. */
function HierarchyPanel({entities,selected,onSelect,filter,onFilter}){
  const list=entities.filter(e=>!filter||(e.tag||e.id).toLowerCase().includes(filter.toLowerCase()));
  return <EditorPanel title="Hierarchy" style={{gridArea:'left'}}
    actions={<Button text="+" variant="ghost" size="small" style={{minWidth:24,height:20,padding:0,fontSize:12}} />}>
    <TextInput value={filter} onChange={onFilter} placeholder="filter" width={0} mono style={{width:'100%',height:24,fontSize:12,marginBottom:8}} />
    <div style={{display:'flex',flexDirection:'column',gap:1}}>
      {list.map(e=>{const on=selected===e.id;return <button key={e.id} type="button" onClick={()=>onSelect(e.id)} style={{
        textAlign:'left',padding:'5px 7px',border:'1px solid '+(on?'var(--action-secondary)':'transparent'),
        background:on?'var(--theme-hover-overlay)':'transparent',
        color:on?'var(--text-heading)':'var(--text-body)',
        fontFamily:'var(--font-mono)',fontSize:12,cursor:'pointer',display:'flex',gap:6,alignItems:'baseline'}}>
        <span style={{color:on?'var(--action-secondary)':'var(--text-faint)'}}>{e.tag?'\u25aa':'\u25ab'}<\/span>
        <span>{e.tag?e.tag:'(untagged)'}<\/span>
        <span style={{color:'var(--text-faint)',fontSize:11}}>({e.id})<\/span>
      <\/button>;})}
      {!list.length&&<Label text="No entities match." fontSize={12} color="var(--text-faint)" />}
    <\/div>
  <\/EditorPanel>;
}

/* pyguara/editor/panels/inspector.py — Entity ID, ResourceLink source + save button,
   separator, then one collapsing header per component drawn by InspectorDrawer. */
function InspectorPanel({entity}){
  const [open,setOpen]=React.useState({});
  if(!entity) return <EditorPanel title="Inspector" style={{gridArea:'right'}}>
    <Label text="No entity selected." fontSize={12} color="var(--text-faint)" />
  <\/EditorPanel>;
  const names=Object.keys(entity.comps);
  return <EditorPanel title="Inspector" style={{gridArea:'right'}}>
    <div style={{fontFamily:'var(--font-mono)',fontSize:12,color:'var(--text-muted)'}}>Entity ID: {entity.id}<\/div>
    {entity.src&&<div style={{marginTop:6}}>
      <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',wordBreak:'break-all'}}>Source: {entity.src}<\/div>
      <Button text="Save to Source Asset" variant="secondary" size="small" style={{marginTop:6,width:'100%',fontSize:11}} />
    <\/div>}
    <hr style={{border:0,borderTop:'1px solid var(--edge)',margin:'10px 0'}} />
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      {names.map(n=>{const isOpen=open[n]!==false;return <div key={n} style={{border:'1px solid var(--edge-subtle)'}}>
        <button type="button" onClick={()=>setOpen(o=>({...o,[n]:!isOpen}))} style={{width:'100%',textAlign:'left',display:'flex',gap:6,alignItems:'center',padding:'6px 8px',background:'var(--surface-raised)',border:0,color:'var(--text-heading)',fontFamily:'var(--font-pixel)',fontSize:12,letterSpacing:'var(--ls-pixel)',cursor:'pointer'}}>
          <span style={{color:'var(--action-secondary)',width:8}}>{isOpen?'\u25be':'\u25b8'}<\/span>{n}
        <\/button>
        {isOpen&&<div style={{padding:'7px 8px',display:'flex',flexDirection:'column',gap:5}}>
          {Object.entries(entity.comps[n]).map(([k,v])=><FieldRow key={k} name={k} value={v} />)}
        <\/div>}
      <\/div>;})}
    <\/div>
  <\/EditorPanel>;
}

/* InspectorDrawer maps field types to imgui widgets: bool -> checkbox,
   float -> drag_float, int -> drag_int, str -> input_text. */
function FieldRow({name,value}){
  const isBool=value==='True'||value==='False';
  const isNum=/^\(?-?[0-9]/.test(value);
  return <label style={{display:'grid',gridTemplateColumns:'82px 1fr',gap:6,alignItems:'center',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-muted)'}}>
    <span style={{overflow:'hidden',textOverflow:'ellipsis'}}>{name}<\/span>
    {isBool
      ? <Checkbox label="" checked={value==='True'} style={{fontSize:11}} />
      : <span style={{background:'var(--surface-inset)',border:'1px solid var(--edge)',padding:'3px 6px',color:isNum?'var(--text-numeric)':'var(--text-body)',fontSize:11,cursor:isNum?'ew-resize':'text',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{value}<\/span>}
  <\/label>;
}

/* pyguara/editor/panels/assets.py — Registry list, separator, Cache (Loaded) list,
   plus a separate Resource Inspector window for the selection. */
function AssetsPanel({selected,onSelect}){
  const D=window.EditorData;
  const [openReg,setOpenReg]=React.useState(true);const [openCache,setOpenCache]=React.useState(true);
  const Head=({label,open,set})=><button type="button" onClick={()=>set(!open)} style={{display:'flex',gap:6,alignItems:'center',background:'none',border:0,padding:'2px 0',color:'var(--text-heading)',fontFamily:'var(--font-pixel)',fontSize:11,letterSpacing:'var(--ls-pixel)',cursor:'pointer'}}><span style={{color:'var(--action-secondary)'}}>{open?'\u25be':'\u25b8'}<\/span>{label}<\/button>;
  const Item=({label,active,onClick})=><button type="button" onClick={onClick} style={{textAlign:'left',padding:'3px 6px',border:0,background:active?'var(--theme-hover-overlay)':'transparent',color:active?'var(--action-secondary)':'var(--text-muted)',fontFamily:'var(--font-mono)',fontSize:11,cursor:'pointer',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{label}<\/button>;
  return <EditorPanel title="Assets" style={{gridArea:'assets'}}>
    <Head label="Registry" open={openReg} set={setOpenReg} />
    {openReg&&<div style={{display:'flex',flexDirection:'column',marginBottom:8}}>
      {D.registry.map(r=><Item key={r} label={r} />)}
    <\/div>}
    <hr style={{border:0,borderTop:'1px solid var(--edge)',margin:'6px 0'}} />
    <Head label="Cache (Loaded)" open={openCache} set={setOpenCache} />
    {openCache&&<div style={{display:'flex',flexDirection:'column'}}>
      {D.cache.map(([t,n,p])=><Item key={p} label={'['+t+'] '+n} active={selected===p} onClick={()=>onSelect(p)} />)}
    <\/div>}
  <\/EditorPanel>;
}

function ResourceInspector({path,onClose}){
  if(!path) return null;
  const D=window.EditorData;const row=D.cache.find(c=>c[2]===path);
  const isData=row&&row[0]==='DataResource';
  return <Panel borderWidth={2} padding="0" style={{position:'absolute',right:16,bottom:16,width:320,zIndex:20,boxShadow:'var(--shadow-stamp-lg)'}}>
    <div style={panelTitle}><span>Resource Inspector<\/span>
      <button type="button" onClick={onClose} style={{background:'none',border:0,color:'var(--text-muted)',cursor:'pointer',fontFamily:'var(--font-mono)',fontSize:13}}>×<\/button><\/div>
    <div style={{padding:10}}>
      <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-muted)',wordBreak:'break-all'}}>Path: {path}<\/div>
      {isData?<>
        <div style={{display:'flex',gap:6,margin:'10px 0'}}>
          <Button text="Save to Disk" size="small" variant="secondary" style={{fontSize:11}} />
          <Button text="Spawn into Scene" size="small" style={{fontSize:11}} />
        <\/div>
        <hr style={{border:0,borderTop:'1px solid var(--edge)',margin:'8px 0'}} />
        <div style={{display:'flex',flexDirection:'column',gap:5}}>
          <FieldRow name="Tag.name" value="guara_player" />
          <FieldRow name="Transform" value="(320.0, 448.0)" />
          <FieldRow name="RigidBody.mass" value="12.0" />
          <FieldRow name="Collider.is_sensor" value="False" />
        <\/div>
      <\/>:<>
        <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-muted)',marginTop:8}}>Type: {row?row[0]:'Resource'}<\/div>
        <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-faint)',marginTop:4}}>Manual editing not supported for this type.<\/div>
      <\/>}
      <Button text="Close" size="small" variant="ghost" onClick={onClose} style={{marginTop:10,fontSize:11}} />
    <\/div>
  <\/Panel>;
}
Object.assign(window,{EditorPanel,HierarchyPanel,InspectorPanel,AssetsPanel,ResourceInspector,FieldRow,panelTitle});