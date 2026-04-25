import { useState } from 'react'
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
  const [at, setAt] = useState<Tab>('protocol')
  const [sr, setSr] = useState(true)

  return (
    <div className="ed" id="experiment-plan-detail-page">
      <div className="ed__c">
        <header className="ed__h animate-fadeIn">
          <div style={{display:'flex',flexDirection:'column',gap:8,maxWidth:800}}>
            <div style={{display:'flex',alignItems:'center',gap:12}}>
              <span className="ed__badge font-label-caps">DRAFT</span>
              <h1 className="font-headline-md" style={{color:'var(--on-surface)'}}>EXP-8492: Graphene Oxide Sensor Calibration</h1>
            </div>
            <p className="font-body-base" style={{color:'var(--on-surface-variant)'}}>
              <span style={{fontWeight:500,color:'var(--on-surface)'}}>Hypothesis:</span> Optimizing thermal reduction at 450°C in argon will increase VOC sensitivity by 25%.
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
                  <span className="font-data-mono" style={{color:'var(--on-surface-variant)'}}>EST. TIME: 14h 30m</span>
                  <div style={{width:1,height:16,background:'var(--outline-variant)'}}/>
                  <span className="font-data-mono" style={{color:'var(--on-surface-variant)'}}>STEPS: 05</span>
                </div>
                <div style={{display:'flex',alignItems:'center',gap:12}}>
                  <span className="font-label-caps" style={{color:'var(--on-surface)'}}>SCIENTIST REVIEW</span>
                  <button className={`ed__toggle ${sr?'ed__toggle--on':''}`} onClick={()=>setSr(!sr)}><span className="ed__toggle-knob"/></button>
                </div>
              </div>
              <div className="ed__steps">
                {steps.map(s=>(
                  <div key={s.n} className="ps" id={`step-${s.n}`}>
                    <div style={{flexShrink:0}}><div className="ps__badge font-data-mono">{s.n}</div></div>
                    <div style={{flex:1,display:'flex',flexDirection:'column',gap:8}}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
                        <h3 style={{fontSize:14,fontWeight:500,color:'var(--on-surface)'}}>{s.t}</h3>
                        <span className="ps__dur font-data-mono">{s.d}</span>
                      </div>
                      <p className="font-body-base" style={{color:'var(--on-surface-variant)'}}>{s.desc}</p>
                      {s.eq&&<div className="ps__eq"><div className="font-label-caps" style={{color:'var(--outline)',marginBottom:4,fontSize:10}}>EQUIPMENT</div><div className="font-data-mono" style={{color:'var(--on-surface-variant)'}}>{s.eq}</div></div>}
                      {s.warn&&<div className="ps__warn"><span className="material-symbols-outlined" style={{fontSize:20,color:'var(--error)'}}>warning</span><div><span className="font-label-caps" style={{color:'var(--error)',display:'block',marginBottom:4}}>CRITICAL NOTE</span><span className="font-body-base" style={{color:'var(--on-surface)'}}>{s.warn}</span></div></div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>}

            {at==='materials'&&<div className="ed__tc animate-fadeIn">
              <div className="mt" id="materials-table">
                <div className="mt__h"><span className="font-label-caps" style={{flex:2}}>Material</span><span className="font-label-caps" style={{flex:1}}>Catalog #</span><span className="font-label-caps" style={{flex:1}}>Supplier</span><span className="font-label-caps" style={{flex:.5,textAlign:'right'}}>Qty</span><span className="font-label-caps" style={{flex:.5,textAlign:'right'}}>Price</span><span className="font-label-caps" style={{flex:.5,textAlign:'center'}}>Status</span></div>
                {mats.map((m,i)=>(<div key={i} className="mt__r"><span className="font-body-base" style={{flex:2,color:'var(--on-surface)'}}>{m.name}</span><span className="font-data-mono" style={{flex:1,color:'var(--primary)'}}>{m.cat}</span><span className="font-body-base" style={{flex:1,color:'var(--on-surface-variant)'}}>{m.sup}</span><span className="font-data-mono" style={{flex:.5,textAlign:'right',color:'var(--on-surface-variant)'}}>{m.qty}</span><span className="font-data-mono" style={{flex:.5,textAlign:'right',color:'var(--on-surface)'}}>{m.p}</span><span style={{flex:.5,textAlign:'center'}}>{m.v?<span className="mt__v font-label-caps"><span className="material-symbols-outlined" style={{fontSize:12}}>check_circle</span>Verified</span>:<span className="mt__u font-label-caps"><span className="material-symbols-outlined" style={{fontSize:12}}>help</span>Verify</span>}</span></div>))}
              </div>
            </div>}

            {at==='budget'&&<div className="ed__tc animate-fadeIn">
              <div className="bp"><div className="bp__sum"><span className="font-label-caps" style={{color:'var(--outline)'}}>ESTIMATED TOTAL</span><span className="font-headline-md" style={{color:'var(--secondary)'}}>$1,059.00</span></div>
                {[{c:'Reagents & Chemicals',n:3,a:'$314'},{c:'Substrates & Consumables',n:2,a:'$225'},{c:'Equipment Consumables',n:4,a:'$445'},{c:'Gas Supplies',n:1,a:'$75'}].map((b,i)=><div key={i} className="bp__row"><div><span className="font-body-base" style={{color:'var(--on-surface)'}}>{b.c}</span><span className="font-data-mono" style={{color:'var(--outline)',marginLeft:8,fontSize:11}}>{b.n} items</span></div><span className="font-data-mono" style={{color:'var(--on-surface)'}}>{b.a}</span></div>)}
              </div>
            </div>}

            {at==='timeline'&&<div className="ed__tc animate-fadeIn"><div className="tp">
              {[{p:'Phase 1: Preparation',d:'1.5 h',s:'1-2',dp:'None'},{p:'Phase 2: Thermal',d:'12 h',s:'3',dp:'Phase 1'},{p:'Phase 3: Fabrication',d:'1 h',s:'4',dp:'Phase 2'},{p:'Phase 4: Characterization',d:'45 min',s:'5',dp:'Phase 3'}].map((t,i,a)=><div key={i} className="tp__phase"><div className="tp__marker"><div className="tp__dot"/>{i<a.length-1&&<div className="tp__line"/>}</div><div className="tp__content"><div className="tp__hdr"><h4 className="font-body-base" style={{fontWeight:600,color:'var(--on-surface)'}}>{t.p}</h4><span className="font-data-mono" style={{color:'var(--primary)'}}>{t.d}</span></div><div style={{display:'flex',gap:16}}><span className="font-label-caps" style={{color:'var(--outline)'}}>Steps: {t.s}</span><span className="font-label-caps" style={{color:'var(--outline)'}}>Depends: {t.dp}</span></div></div></div>)}
            </div></div>}

            {at==='validation'&&<div className="ed__tc animate-fadeIn"><div className="vp">
              {[{ok:true,t:'Protocol Completeness',d:'All fields populated. 5/5 steps have durations.'},{ok:true,t:'Materials Cross-Reference',d:'4/5 materials verified.'},{ok:false,t:'Unverified Supplier',d:'Argon Gas (AR-UHP) — Verify before ordering.'},{ok:true,t:'Timeline Consistency',d:'All dependencies satisfied.'}].map((v,i)=><div key={i} className={`vp__item vp__item--${v.ok?'pass':'warn'}`}><span className="material-symbols-outlined" style={{color:v.ok?'var(--secondary)':'var(--tertiary)',fontSize:20}}>{v.ok?'check_circle':'warning'}</span><div><span className="font-body-base" style={{fontWeight:500,color:'var(--on-surface)'}}>{v.t}</span><p className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:13}}>{v.d}</p></div></div>)}
            </div></div>}

            {at==='literature'&&<div className="ed__tc animate-fadeIn"><div className="lp">
              {[{tag:'PRIMARY',t:'Thermal Reduction of GO for Gas Sensing',r:'Zhang et al., ACS Nano, 2023',d:'Thermal reduction at 400-500°C produces optimal rGO for VOC detection.'},{tag:'SUPPORTING',t:'Comparative Study of GO Reduction Methods',r:'Kim et al., Carbon, 2022',d:'Chemical vs thermal: 15% baseline variance with hydrazine.'},{tag:'NOVELTY',t:'Novelty Signal: MODERATE',r:'',d:'450°C + interdigitated Au electrodes for multi-VOC detection has limited prior art.'}].map((l,i)=><div key={i} className="lp__item"><div className="lp__tag font-label-caps">{l.tag}</div><h4 className="font-body-base" style={{fontWeight:500,color:'var(--on-surface)',marginBottom:4}}>{l.t}</h4>{l.r&&<p className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:11}}>{l.r}</p>}<p className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:12,marginTop:8}}>{l.d}</p></div>)}
            </div></div>}
          </div>

          <div className="ed__side">
            <div className="ed__insight animate-slideInRight" id="knowledge-insight">
              <div className="ed__insight-glow"/>
              <div style={{padding:16,display:'flex',flexDirection:'column',gap:16}}>
                <div style={{display:'flex',alignItems:'center',gap:8,color:'var(--tertiary)'}}><span className="material-symbols-outlined" style={{fontSize:20,fontVariationSettings:"'FILL' 1"}}>psychology</span><span className="font-label-caps">KNOWLEDGE GARDEN INSIGHT</span></div>
                <p className="font-body-base" style={{color:'var(--on-surface)'}}>Protocol adjusted based on historical data. Previous calibrations using Hydrazine showed 15% variance in baseline resistance over 48 hours.</p>
                <div className="ed__ref"><div className="font-label-caps" style={{color:'var(--outline)',marginBottom:8}}>REFERENCED EXPERIMENT</div><div className="font-data-mono" style={{color:'var(--primary)'}}>EXP-7102</div><div className="font-body-base" style={{color:'var(--on-surface-variant)',fontSize:12,marginTop:4}}>"Long-term stability of chemically reduced GO gas sensors"</div></div>
                <div style={{display:'flex',alignItems:'center',gap:8,paddingTop:8,borderTop:'1px solid rgba(66,71,84,0.2)'}}><div style={{width:8,height:8,borderRadius:'50%',background:'var(--secondary-container)'}}/><span className="font-data-mono" style={{color:'var(--on-surface-variant)',fontSize:11}}>System confidence: 94%</span></div>
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
