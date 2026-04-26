import { useMemo, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { loadPlan } from '../../lib/api'
import type { ExperimentPlan } from '../../types/plan'
import './ExperimentPlanDetail.css'

const steps = [
  { n: '01', t: 'Substrate Preparation', d: '30 min', desc: 'Clean SiO2/Si substrates using standard RCA sequence. Rinse with DI water (18.2 MΩ·cm) and blow dry with N2.', eq: 'Ultrasonic Bath, Spin Coater, N2 Gun' },
  { n: '02', t: 'Graphene Oxide Spin Coating', d: '45 min', desc: 'Dispense 50 µL of 2mg/mL GO dispersion. Spin at 3000 rpm for 60s.', warn: 'Ensure dispersion is completely homogenized before dispensing to prevent aggregate formation.' },
  { n: '03', t: 'Thermal Reduction', d: '12 h', desc: 'Purge with Argon (200 sccm) for 30 mins. Ramp to 450°C at 5°C/min. Hold 2 hours, cool under Argon.' },
  { n: '04', t: 'Electrode Deposition', d: '1 h', desc: 'Deposit 5nm Cr + 100nm Au contacts via thermal evaporation through shadow mask.', eq: 'Thermal Evaporator, Shadow Mask Set' },
  { n: '05', t: 'VOC Sensitivity Testing', d: '45 min', desc: 'Expose to VOCs (acetone, ethanol, toluene) at 1-100 ppm. Record ΔR/R0.', eq: 'Gas Chamber, MFCs, Keithley 2400' },
]

const mats = [
  { name: 'GO Dispersion (2mg/mL)', cat: '763713', sup: 'Sigma-Aldrich', qty: '100 mL', p: '$89', v: true },
  { name: 'SiO2/Si Wafer (4")', cat: 'WS-SIO2-4', sup: 'UniversityWafer', qty: '5 pcs', p: '$45', v: true },
  { name: 'Cr Pellets (99.99%)', cat: 'EVMCR35B', sup: 'Kurt J. Lesker', qty: '25 g', p: '$120', v: true },
  { name: 'Au Wire (99.99%)', cat: 'EVMAU40G', sup: 'Kurt J. Lesker', qty: '10 g', p: '$250', v: true },
  { name: 'Argon Gas (UHP)', cat: 'AR-UHP', sup: 'Airgas', qty: '1 cyl', p: '$75', v: false },
]

type Tab = 'protocol'|'materials'|'budget'|'timeline'|'validation'|'literature'
const tabs: {id:Tab;l:string;i:string}[] = [
  {id:'protocol',l:'PROTOCOL',i:'assignment'},{id:'materials',l:'MATERIALS',i:'science'},
  {id:'budget',l:'BUDGET',i:'payments'},{id:'timeline',l:'TIMELINE',i:'calendar_month'},
  {id:'validation',l:'VALIDATION',i:'verified'},{id:'literature',l:'LITERATURE',i:'menu_book'},
]

export default function ExperimentPlanDetail() {
  const { id } = useParams()
  const location = useLocation()
  const routePlan = (location.state as { plan?: ExperimentPlan } | null)?.plan
  const currentPlan = useMemo(() => {
    if (routePlan) {
      return routePlan
    }
    if (id) {
      return loadPlan(id)
    }
    return null
  }, [id, routePlan])
  const [at, setAt] = useState<Tab>('protocol')
  const [sr, setSr] = useState(true)

  const protocolSteps = currentPlan?.protocol.steps ?? steps.map((s, index) => ({
    step_number: index + 1,
    action: s.t,
    duration: s.d,
    details: s.desc,
    notes: s.warn,
    source: undefined,
  }))
  const materials = currentPlan?.materials ?? mats.map((m) => ({
    item: m.name,
    catalog_number: m.cat,
    supplier: m.sup,
    quantity: m.qty,
    unit_price: Number(m.p.replace(/[^0-9.]/g, '')) || 0,
    currency: 'USD',
    total_price: Number(m.p.replace(/[^0-9.]/g, '')) || 0,
    verification: m.v ? 'verified' : 'suggested_verify',
  }))
  const literature = currentPlan?.literature_qc.references ?? []

  return (
    <div className="ed" id="experiment-plan-detail-page">
      <div className="ed__c">
        <header className="ed__h animate-fadeIn">
          <div style={{display:'flex',flexDirection:'column',gap:8,maxWidth:800}}>
            <div style={{display:'flex',alignItems:'center',gap:12}}>
              <span className="ed__badge font-label-caps">DRAFT</span>
              <h1 className="font-headline-md" style={{color:'var(--on-surface)'}}>{currentPlan?.title ?? 'EXP-8492: Graphene Oxide Sensor Calibration'}</h1>
            </div>
            <p className="font-body-base" style={{color:'var(--on-surface-variant)'}}>
              <span style={{fontWeight:500,color:'var(--on-surface)'}}>Hypothesis:</span> {currentPlan?.hypothesis ?? 'Optimizing thermal reduction at 450°C in argon will increase VOC sensitivity by 25%.'}
            </p>
          </div>
          <button className="ed__export" id="export-pdf-btn">
            <span className="material-symbols-outlined" style={{fontSize:18}}>picture_as_pdf</span>
            <span className="font-label-caps">EXPORT PDF</span>
          </button>
        </header>

        <div className="ed__grid">
          <div className="ed__main">
            <div className="ed__tabs" id="plan-tabs">
              {tabs.map(t=>(
                <button key={t.id} className={`ed__tab ${at===t.id?'ed__tab--active':''}`} onClick={()=>setAt(t.id)} id={`tab-${t.id}`}>
                  <span className="material-symbols-outlined" style={{fontSize:18,fontVariationSettings:at===t.id?"'FILL' 1":"'FILL' 0"}}>{t.i}</span>
                  <span className="font-label-caps">{t.l}</span>
                </button>
              ))}
            </div>

            {at==='protocol'&&<div className="ed__tc animate-fadeIn">
              <div className="ed__toolbar">
                <div style={{display:'flex',alignItems:'center',gap:16}}>
                  <span className="font-data-mono" style={{color:'var(--on-surface-variant)'}}>EST. TIME: {currentPlan?.protocol.total_duration ?? '14h 30m'}</span>
                  <div style={{width:1,height:16,background:'var(--outline-variant)'}}/>
                  <span className="font-data-mono" style={{color:'var(--on-surface-variant)'}}>STEPS: {String(protocolSteps.length).padStart(2, '0')}</span>
                </div>
                <div style={{display:'flex',alignItems:'center',gap:12}}>
                  <span className="font-label-caps" style={{color:'var(--on-surface)'}}>SCIENTIST REVIEW</span>
                  <button className={`ed__toggle ${sr?'ed__toggle--on':''}`} onClick={()=>setSr(!sr)}><span className="ed__toggle-knob"/></button>
                </div>
              </div>
              <div className="ed__steps">
                {protocolSteps.map(s=>(
                  <div key={s.step_number} className="ps" id={`step-${s.step_number}`}>
                    <div style={{flexShrink:0}}><div className="ps__badge font-data-mono">{String(s.step_number).padStart(2, '0')}</div></div>
                    <div style={{flex:1,display:'flex',flexDirection:'column',gap:8}}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
                        <h3 style={{fontSize:14,fontWeight:500,color:'var(--on-surface)'}}>{s.action}</h3>
                        <span className="ps__dur font-data-mono">{s.duration}</span>
                      </div>
                      <p className="font-body-base" style={{color:'var(--on-surface-variant)'}}>{s.details}</p>
                      {s.notes&&<div className="ps__warn"><span className="material-symbols-outlined" style={{fontSize:20,color:'var(--error)'}}>warning</span><div><span className="font-label-caps" style={{color:'var(--error)',display:'block',marginBottom:4}}>CRITICAL NOTE</span><span className="font-body-base" style={{color:'var(--on-surface)'}}>{s.notes}</span></div></div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>}

            {at==='materials'&&<div className="ed__tc animate-fadeIn">
              <div className="mt" id="materials-table">
                <div className="mt__h"><span className="font-label-caps" style={{flex:2}}>Material</span><span className="font-label-caps" style={{flex:1}}>Catalog #</span><span className="font-label-caps" style={{flex:1}}>Supplier</span><span className="font-label-caps" style={{flex:.5,textAlign:'right'}}>Qty</span><span className="font-label-caps" style={{flex:.5,textAlign:'right'}}>Price</span><span className="font-label-caps" style={{flex:.5,textAlign:'center'}}>Status</span></div>
                {materials.map((m,i)=>(<div key={i} className="mt__r"><span className="font-body-base" style={{flex:2,color:'var(--on-surface)'}}>{m.item}</span><span className="font-data-mono" style={{flex:1,color:'var(--on-surface)'}}>{m.catalog_number}</span><span className="font-body-base" style={{flex:1,color:'var(--on-surface-variant)'}}>{m.supplier}</span><span className="font-data-mono" style={{flex:.5,textAlign:'right',color:'var(--on-surface-variant)'}}>{m.quantity}</span><span className="font-data-mono" style={{flex:.5,textAlign:'right',color:'var(--on-surface)'}}>{m.currency} {m.total_price.toFixed(2)}</span><span style={{flex:.5,textAlign:'center'}}>{m.verification === 'verified'?<span className="mt__v font-label-caps"><span className="material-symbols-outlined" style={{fontSize:12}}>check_circle</span>Verified</span>:<span className="mt__u font-label-caps"><span className="material-symbols-outlined" style={{fontSize:12}}>help</span>Verify</span>}</span></div>))}
              </div>
            </div>}

            {at==='budget'&&<div className="ed__tc animate-fadeIn">
              <div className="bp"><div className="bp__sum"><span className="font-label-caps" style={{color:'var(--outline)'}}>ESTIMATED TOTAL</span><span className="font-headline-md" style={{color:'var(--on-surface)',fontWeight:500,letterSpacing:'-0.01em'}}>{currentPlan?.budget.currency ?? '$'} {currentPlan?.budget.total.toFixed(2) ?? '1,059.00'}</span></div>
                {[{c:'Reagents',a:currentPlan?.budget.breakdown.reagents},{c:'Consumables',a:currentPlan?.budget.breakdown.consumables},{c:'Equipment Usage',a:currentPlan?.budget.breakdown.equipment_usage}].map((b,i)=><div key={i} className="bp__row"><div><span className="font-body-base" style={{color:'var(--on-surface)'}}>{b.c}</span></div><span className="font-data-mono" style={{color:'var(--on-surface)'}}>{currentPlan?.budget.currency ?? 'EUR'} {Number(b.a ?? 0).toFixed(2)}</span></div>)}
              </div>
            </div>}

            {at==='timeline'&&<div className="ed__tc animate-fadeIn"><div className="tp">
              {(currentPlan?.timeline.phases ?? [{ phase: 'Phase 1', duration: '1 day', tasks: ['Preparation'], dependencies: [] }]).map((t,i,a)=><div key={i} className="tp__phase"><div className="tp__marker"><div className="tp__dot"/>{i<a.length-1&&<div className="tp__line"/>}</div><div className="tp__content"><div className="tp__hdr"><h4 className="font-body-base" style={{fontWeight:600,color:'var(--on-surface)'}}>{t.phase}</h4><span className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:12}}>{t.duration}</span></div><div style={{display:'flex',gap:16}}><span className="font-label-caps" style={{color:'var(--outline)'}}>Tasks: {t.tasks.length}</span><span className="font-label-caps" style={{color:'var(--outline)'}}>Depends: {t.dependencies.join(', ') || 'None'}</span></div></div></div>)}
            </div></div>}

            {at==='validation'&&<div className="ed__tc animate-fadeIn"><div className="vp">
              {(currentPlan?.review_issues.length ? currentPlan.review_issues.map((issue) => ({ ok: issue.severity !== 'error', t: issue.path, d: issue.message })) : [{ok:true,t:'Protocol Completeness',d:'No critical issues flagged.'}]).map((v,i)=><div key={i} className={`vp__item vp__item--${v.ok?'pass':'warn'}`}><span className="material-symbols-outlined" style={{color:v.ok?'var(--on-surface-variant)':'var(--tertiary)',fontSize:20}}>{v.ok?'check_circle':'warning'}</span><div><span className="font-body-base" style={{fontWeight:500,color:'var(--on-surface)'}}>{v.t}</span><p className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:13}}>{v.d}</p></div></div>)}
            </div></div>}

            {at==='literature'&&<div className="ed__tc animate-fadeIn"><div className="lp">
              {(literature.length ? literature.map((l) => ({ tag: currentPlan?.literature_qc.novelty_signal ?? 'REFERENCE', t: l.title, r: [l.authors, l.journal, l.year].filter(Boolean).join(', '), d: l.key_difference ?? l.similarity ?? 'Reference from literature scout.' })) : [{tag:'NOVELTY',t:'No references found',r:'',d:currentPlan?.literature_qc.summary ?? 'No literature data available.'}]).map((l,i)=><div key={i} className="lp__item"><div className="lp__tag font-label-caps">{l.tag}</div><h4 className="font-body-base" style={{fontWeight:500,color:'var(--on-surface)',marginBottom:4}}>{l.t}</h4>{l.r&&<p className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:11}}>{l.r}</p>}<p className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:12,marginTop:8}}>{l.d}</p></div>)}
            </div></div>}
          </div>

          <div className="ed__side">
            <div className="ed__insight animate-slideInRight" id="knowledge-insight">
              <div className="ed__insight-glow"/>
              <div style={{padding:16,display:'flex',flexDirection:'column',gap:16}}>
                <div style={{display:'flex',alignItems:'center',gap:8,color:'var(--on-surface-variant)'}}><span className="material-symbols-outlined" style={{fontSize:18}}>psychology</span><span className="font-label-caps">KNOWLEDGE GARDEN INSIGHT</span></div>
                <p className="font-body-base" style={{color:'var(--on-surface)'}}>Protocol adjusted based on historical data. Previous calibrations using Hydrazine showed 15% variance in baseline resistance over 48 hours.</p>
                <div className="ed__ref"><div className="font-label-caps" style={{color:'var(--outline)',marginBottom:6}}>REFERENCED EXPERIMENT</div><div className="font-data-mono" style={{color:'var(--on-surface)'}}>EXP-7102</div><div className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:12,marginTop:4}}>"Long-term stability of chemically reduced GO gas sensors"</div></div>
                <div style={{display:'flex',alignItems:'center',gap:8,paddingTop:8,borderTop:'1px solid var(--border-faintest)'}}><div style={{width:6,height:6,borderRadius:'50%',background:'var(--primary)'}}/><span className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:11}}>System confidence: 94%</span></div>
              </div>
            </div>
            <div className="ed__meta animate-slideInRight" style={{animationDelay:'0.1s'}} id="experiment-metadata">
              <div className="font-label-caps" style={{color:'var(--outline)',marginBottom:12}}>EXPERIMENT METADATA</div>
              {[['Author Agent','Chem_Synth_V2'],['Version','1.0.4-draft'],['Target','ΔR/R0 > 20% @ 10ppm']].map(([l,v],i)=><div key={i} className="ed__meta-row" style={i===2?{borderBottom:'none'}:undefined}><span className="font-body-base" style={{color:'var(--on-surface-variant)'}}>{l}</span><span className="font-data-mono" style={{color:'var(--on-surface)'}}>{v}</span></div>)}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
