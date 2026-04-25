import { useState, useEffect, useCallback } from 'react'
import './KnowledgeGarden.css'

interface KNode { id:string; type:'experiment'|'correction'|'reagent'; x:number; y:number; size:number; title?:string; conf?:string; applied?:number; abstract?:string; conns?:{id:string;label:string;type:'experiment'|'correction'|'reagent'}[] }

const nodes: KNode[] = [
  { id:'EXP-992',type:'experiment',x:400,y:300,size:64,title:'Quantum Alignment Vector',conf:'94.2%',applied:128,abstract:'Observation of stable quantum states under high thermal load. The alignment vector suggests a novel pathway for reducing decoherence in multi-qubit systems.',conns:[{id:'EXP-841',label:'EXP-841: Thermal Baseline',type:'experiment'},{id:'COR-092',label:'COR-092: Drift Adjustment',type:'correction'},{id:'RGT-11',label:'RGT-11: Cooling Matrix A',type:'reagent'}] },
  { id:'COR-001',type:'correction',x:250,y:200,size:48 },
  { id:'RGT-01',type:'reagent',x:550,y:180,size:40 },
  { id:'EXP-841',type:'experiment',x:600,y:400,size:56 },
  { id:'RGT-02',type:'reagent',x:300,y:450,size:24 },
  { id:'COR-002',type:'correction',x:700,y:350,size:32 },
  { id:'RGT-03',type:'reagent',x:650,y:500,size:20 },
  { id:'EXP-100',type:'experiment',x:150,y:150,size:28 },
  { id:'COR-003',type:'correction',x:180,y:280,size:24 },
]

const edges = [
  {f:'EXP-992',t:'COR-001'},{f:'EXP-992',t:'RGT-01'},{f:'EXP-992',t:'EXP-841',h:true},{f:'EXP-992',t:'RGT-02'},
  {f:'EXP-841',t:'COR-002'},{f:'EXP-841',t:'RGT-03'},{f:'COR-001',t:'EXP-100'},{f:'COR-001',t:'COR-003'},
]

const tc: Record<string,{bg:string;border:string;dot:string}> = {
  experiment:{bg:'var(--surface-container)',border:'var(--primary-container)',dot:'var(--primary)'},
  correction:{bg:'var(--surface-container)',border:'var(--tertiary-container)',dot:'var(--tertiary)'},
  reagent:{bg:'var(--surface-container)',border:'var(--secondary-container)',dot:'var(--secondary)'},
}

export default function KnowledgeGarden() {
  const [sel, setSel] = useState<KNode>(nodes[0])
  const [filter, setFilter] = useState('')
  const [hov, setHov] = useState<string|null>(null)
  const [pos, setPos] = useState(nodes.map(n=>({...n})))

  useEffect(()=>{
    let id: number; const st=Date.now()
    const anim=()=>{const e=(Date.now()-st)/1000;setPos(nodes.map((n,i)=>({...n,x:n.x+Math.sin(e*0.5+i*1.2)*3,y:n.y+Math.cos(e*0.3+i*0.8)*3})));id=requestAnimationFrame(anim)}
    anim();return()=>cancelAnimationFrame(id)
  },[])

  const gp=useCallback((id:string)=>{const n=pos.find(n=>n.id===id);return n?{x:n.x,y:n.y}:{x:0,y:0}},[pos])

  return (
    <div className="kg" id="knowledge-garden-page">
      <div className="kg__canvas">
        <div className="kg__dotbg"/>
        <div className="kg__ctrl" id="graph-controls">
          <div className="kg__ctrl-inner">
            <button className="kg__btn" title="Zoom In"><span className="material-symbols-outlined" style={{fontSize:20}}>add</span></button>
            <button className="kg__btn" title="Zoom Out"><span className="material-symbols-outlined" style={{fontSize:20}}>remove</span></button>
            <div className="kg__div"/>
            <button className="kg__btn" title="Reset"><span className="material-symbols-outlined" style={{fontSize:20}}>fit_screen</span></button>
          </div>
        </div>
        <div className="kg__legend" id="graph-legend">
          <h4 className="font-label-caps" style={{color:'var(--on-surface-variant)',marginBottom:12}}>Node Legend</h4>
          {[{c:'var(--primary)',l:'Experiments'},{c:'var(--tertiary)',l:'Corrections'},{c:'var(--secondary)',l:'Reagents'}].map(x=><div key={x.l} className="kg__legend-item"><div className="kg__legend-dot" style={{background:x.c}}/><span className="font-data-mono" style={{fontSize:12,color:'var(--on-surface)'}}>{x.l}</span></div>)}
        </div>
        <svg className="kg__edges" viewBox="0 0 800 600">
          {edges.map((e,i)=>{const f=gp(e.f),t=gp(e.t);return<line key={i} x1={f.x} y1={f.y} x2={t.x} y2={t.y} stroke={e.h?'var(--primary-container)':'var(--outline-variant)'} strokeWidth={e.h?2:1}/>})}
        </svg>
        {pos.map(n=>{const c=tc[n.type],isSel=sel.id===n.id,isHov=hov===n.id;return(
          <div key={n.id} className={`kg__node ${isSel?'kg__node--sel':''}`} style={{left:n.x,top:n.y,width:n.size,height:n.size,background:c.bg,borderColor:isSel||isHov?c.dot:c.border,boxShadow:'none',transform:`translate(-50%,-50%) ${isHov?'scale(1.06)':'scale(1)'}`}} onClick={()=>{const fn=nodes.find(x=>x.id===n.id);if(fn)setSel(fn)}} onMouseEnter={()=>setHov(n.id)} onMouseLeave={()=>setHov(null)} id={`node-${n.id}`}>
            {n.size>=40?<span className="material-symbols-outlined" style={{fontSize:n.size>=56?24:18,color:c.dot,opacity:0.7}}>{n.type==='experiment'?'science':n.type==='correction'?'tune':'water_drop'}</span>:<div style={{width:n.size*0.2,height:n.size*0.2,borderRadius:'50%',background:c.dot}}/>}
            {isSel&&n.id&&<div className="kg__node-label font-data-mono">{n.id}</div>}
          </div>
        )})}
      </div>
      <div className="kg__panel" id="node-detail-panel">
        <div className="kg__filter"><div className="kg__filter-in"><span className="material-symbols-outlined" style={{fontSize:18,color:'var(--outline)'}}>filter_list</span><input className="font-data-mono" placeholder="Filter nodes..." value={filter} onChange={e=>setFilter(e.target.value)} id="node-filter-input"/></div></div>
        <div className="kg__detail">
          <div className="kg__dh"><div className="kg__di"><span className="material-symbols-outlined" style={{color:'var(--primary)',fontVariationSettings:"'FILL' 1"}}>science</span></div><div><h3 className="font-headline-md" style={{color:'var(--on-surface)',marginBottom:4}}>{sel.title||sel.id}</h3><div style={{display:'flex',gap:8}}><span className="kg__tag kg__tag--blue font-label-caps">{sel.id}</span><span className="kg__tag kg__tag--neutral font-label-caps">PHYSICS</span></div></div></div>
          <div className="kg__db">
            <div className="kg__stats"><div><div className="font-label-caps" style={{color:'var(--outline)',fontSize:10,marginBottom:4}}>Confidence</div><div className="font-data-mono" style={{color:'var(--secondary)',fontSize:18}}>{sel.conf||'N/A'}</div></div><div><div className="font-label-caps" style={{color:'var(--outline)',fontSize:10,marginBottom:4}}>Times Applied</div><div className="font-data-mono" style={{color:'var(--on-surface)',fontSize:18}}>{sel.applied||0}</div></div></div>
            <div><h4 className="font-label-caps" style={{color:'var(--outline)',marginBottom:8}}>ABSTRACT / CONTENT</h4><p className="font-body-base" style={{color:'var(--on-surface)',fontSize:14}}>{sel.abstract||'No content available.'}</p></div>
            {sel.conns&&<div><div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-end',marginBottom:12}}><h4 className="font-label-caps" style={{color:'var(--outline)'}}>PRIMARY CONNECTIONS</h4><span className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:12}}>{sel.conns.length} Direct</span></div><div className="kg__conn-list">{sel.conns.map(c=><div key={c.id} className="kg__conn-item"><div style={{width:8,height:8,borderRadius:'50%',background:tc[c.type].dot,flexShrink:0}}/><span className="font-data-mono" style={{color:'var(--on-surface)',fontSize:13}}>{c.label}</span></div>)}</div></div>}
          </div>
        </div>
        <div className="kg__action"><button className="kg__action-btn font-data-mono" id="link-source-btn"><span className="material-symbols-outlined" style={{fontSize:18}}>open_in_new</span>Link to Source Experiment</button></div>
      </div>
    </div>
  )
}
