import { useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { acceptPlanDraft, loadPlan } from '../../lib/api'
import type { AcceptDraftResponse, ExperimentPlan } from '../../types/plan'
import './ExperimentPlanDetail.css'

type Tab = 'protocol' | 'materials' | 'budget' | 'timeline' | 'validation' | 'literature'
const tabs: { id: Tab; l: string; i: string }[] = [
  { id: 'protocol', l: 'PROTOCOL', i: 'assignment' },
  { id: 'materials', l: 'MATERIALS', i: 'science' },
  { id: 'budget', l: 'BUDGET', i: 'payments' },
  { id: 'timeline', l: 'TIMELINE', i: 'calendar_month' },
  { id: 'validation', l: 'VALIDATION', i: 'verified' },
  { id: 'literature', l: 'LITERATURE', i: 'menu_book' },
]

const formatMoney = (value: number, currency: string): string => {
  if (!Number.isFinite(value)) return `${currency} 0.00`
  return `${currency} ${value.toFixed(2)}`
}

const noveltyLabel = (signal: string | undefined): string => {
  if (signal === 'exact_match') return 'EXACT MATCH'
  if (signal === 'similar_work_exists') return 'SIMILAR WORK'
  if (signal === 'not_found') return 'NOVEL'
  return 'REFERENCE'
}

export default function ExperimentPlanDetail() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const routePlan = (location.state as { plan?: ExperimentPlan } | null)?.plan
  const currentPlan = useMemo<ExperimentPlan | null>(() => {
    if (routePlan) return routePlan
    if (id) return loadPlan(id)
    return null
  }, [id, routePlan])
  const [at, setAt] = useState<Tab>('protocol')
  const initialGraphStatus = (currentPlan?.metadata?.graph_status as string | undefined) ?? 'draft'
  const [graphStatus, setGraphStatus] = useState<string>(initialGraphStatus)
  const [accepting, setAccepting] = useState(false)
  const [acceptResult, setAcceptResult] = useState<AcceptDraftResponse | null>(null)
  const [acceptError, setAcceptError] = useState<string | null>(null)

  const planId = currentPlan?.plan_id ?? id ?? null

  const handleAccept = async (): Promise<void> => {
    if (!planId || accepting) return
    setAccepting(true)
    setAcceptError(null)
    try {
      const result = await acceptPlanDraft(planId)
      setAcceptResult(result)
      setGraphStatus('active')
    } catch (err) {
      setAcceptError(err instanceof Error ? err.message : 'Accept failed')
    } finally {
      setAccepting(false)
    }
  }

  const handleExport = (): void => {
    if (typeof window !== 'undefined') {
      window.print()
    }
  }

  if (!currentPlan) {
    return (
      <div className="ed" id="experiment-plan-detail-page">
        <div className="ed__c">
          <div className="ed__empty animate-fadeIn" style={{ padding: 48, textAlign: 'center' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 48, color: 'var(--outline)' }}>science_off</span>
            <h2 className="font-headline-md" style={{ marginTop: 16, color: 'var(--on-surface)' }}>Plan not available</h2>
            <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', marginTop: 8 }}>
              The plan could not be loaded. Start a new run to generate an experiment draft.
            </p>
            <button
              className="ed__export"
              style={{ marginTop: 24, background: 'var(--primary)', color: 'var(--on-primary)', borderColor: 'var(--primary)' }}
              onClick={() => navigate('/')}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add_circle</span>
              <span className="font-label-caps">NEW EXPERIMENT</span>
            </button>
          </div>
        </div>
      </div>
    )
  }

  const isActive = graphStatus === 'active'
  const badgeLabel = isActive ? 'ACTIVE' : 'DRAFT'

  const protocolSteps = currentPlan.protocol.steps ?? []
  const materials = currentPlan.materials ?? []
  const literature = currentPlan.literature_qc.references ?? []
  const validation = currentPlan.validation
  const reviewIssues = currentPlan.review_issues ?? []

  const budgetCurrency = currentPlan.budget.currency || 'USD'
  const budgetTotal = currentPlan.budget.total ?? 0
  const budgetBreakdown = currentPlan.budget.breakdown ?? { reagents: 0, consumables: 0, equipment_usage: 0 }

  const experimentType = (currentPlan.metadata?.experiment_type as string | undefined) ?? 'general'
  const generatedBy = (currentPlan.metadata?.generated_by as string | undefined) ?? 'multi-agent'
  const generatedAt = currentPlan.generated_at
    ? new Date(currentPlan.generated_at).toLocaleString()
    : '—'
  const knowledgeNodeCount = currentPlan.knowledge_nodes_extracted?.length ?? 0
  const candidateSummary = (currentPlan.metadata?.candidate_summary as Record<string, number> | undefined) ?? null

  return (
    <div className="ed" id="experiment-plan-detail-page">
      <div className="ed__c">
        <header className="ed__h animate-fadeIn">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 800 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span
                className="ed__badge font-label-caps"
                style={isActive ? { background: 'color-mix(in srgb, var(--primary) 14%, transparent)', color: 'var(--primary)' } : undefined}
              >{badgeLabel}</span>
              <h1 className="font-headline-md" style={{ color: 'var(--on-surface)' }}>{currentPlan.title}</h1>
            </div>
            <p className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>
              <span style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Hypothesis:</span> {currentPlan.hypothesis}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {!isActive && (
              <button
                className="ed__export"
                id="accept-draft-btn"
                onClick={handleAccept}
                disabled={accepting || !planId}
                style={{
                  background: 'var(--primary)',
                  color: 'var(--on-primary)',
                  borderColor: 'var(--primary)',
                  opacity: accepting ? 0.65 : 1,
                  cursor: accepting ? 'wait' : 'pointer',
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                  {accepting ? 'hourglass_top' : 'task_alt'}
                </span>
                <span className="font-label-caps">{accepting ? 'INGESTING…' : 'ACCEPT DRAFT'}</span>
              </button>
            )}
            <button className="ed__export" id="export-pdf-btn" onClick={handleExport}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>picture_as_pdf</span>
              <span className="font-label-caps">EXPORT PDF</span>
            </button>
          </div>
        </header>

        {(acceptResult || acceptError) && (
          <div
            className="animate-fadeIn"
            style={{
              padding: '12px 16px',
              borderRadius: 8,
              border: '1px solid var(--outline-variant)',
              background: 'var(--surface-container-lowest)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
            }}
          >
            {acceptResult ? (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span className="font-label-caps" style={{ color: 'var(--primary)' }}>DRAFT INGESTED</span>
                  <span className="font-body-base" style={{ color: 'var(--on-surface)' }}>
                    <strong>{acceptResult.inserted_nodes}</strong> new nodes · <strong>{acceptResult.merged_nodes}</strong> deduplicated · <strong>{acceptResult.inserted_edges}</strong> edges
                  </span>
                </div>
                <button
                  className="ed__export"
                  onClick={() => navigate('/knowledge-garden')}
                  style={{ borderColor: 'var(--primary)', color: 'var(--primary)' }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>account_tree</span>
                  <span className="font-label-caps">OPEN GRAPH</span>
                </button>
              </>
            ) : (
              <span className="font-body-base" style={{ color: 'var(--error)' }}>
                {acceptError}
              </span>
            )}
          </div>
        )}

        <div className="ed__grid">
          <div className="ed__main">
            <div className="ed__tabs" id="plan-tabs">
              {tabs.map(t => (
                <button key={t.id} className={`ed__tab ${at === t.id ? 'ed__tab--active' : ''}`} onClick={() => setAt(t.id)} id={`tab-${t.id}`}>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, fontVariationSettings: at === t.id ? "'FILL' 1" : "'FILL' 0" }}>{t.i}</span>
                  <span className="font-label-caps">{t.l}</span>
                </button>
              ))}
            </div>

            {at === 'protocol' && (
              <div className="ed__tc animate-fadeIn">
                <div className="ed__toolbar">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <span className="font-data-mono" style={{ color: 'var(--on-surface-variant)' }}>STEPS: {String(protocolSteps.length).padStart(2, '0')}</span>
                  </div>
                </div>
                {protocolSteps.length === 0 ? (
                  <div className="font-body-base" style={{ padding: 32, color: 'var(--on-surface-variant)', textAlign: 'center' }}>
                    Kein Protokoll vorhanden.
                  </div>
                ) : (
                  <div className="ed__steps">
                    {protocolSteps.map(s => (
                      <div key={s.step_number} className="ps" id={`step-${s.step_number}`}>
                        <div style={{ flexShrink: 0 }}><div className="ps__badge font-data-mono">{String(s.step_number).padStart(2, '0')}</div></div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <h3 style={{ fontSize: 14, fontWeight: 500, color: 'var(--on-surface)' }}>{s.action}</h3>
                          <p className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>{s.details}</p>
                          {s.notes && (
                            <div className="ps__warn">
                              <span className="material-symbols-outlined" style={{ fontSize: 20, color: 'var(--error)' }}>warning</span>
                              <div>
                                <span className="font-label-caps" style={{ color: 'var(--error)', display: 'block', marginBottom: 4 }}>CRITICAL NOTE</span>
                                <span className="font-body-base" style={{ color: 'var(--on-surface)' }}>{s.notes}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {at === 'materials' && (
              <div className="ed__tc animate-fadeIn">
                {materials.length === 0 ? (
                  <div className="font-body-base" style={{ padding: 32, color: 'var(--on-surface-variant)', textAlign: 'center' }}>
                    Keine Materialien identifiziert.
                  </div>
                ) : (
                  <>
                    <div className="mt" id="materials-table">
                      <div className="mt__h">
                        <span className="font-label-caps" style={{ flex: 2 }}>Material</span>
                        <span className="font-label-caps" style={{ flex: 1 }}>Catalog #</span>
                        <span className="font-label-caps" style={{ flex: 1 }}>Supplier</span>
                        <span className="font-label-caps" style={{ flex: .5, textAlign: 'right' }}>Qty</span>
                        <span className="font-label-caps" style={{ flex: .5, textAlign: 'right' }}>Price</span>
                        <span className="font-label-caps" style={{ flex: .8, textAlign: 'center' }}>Status</span>
                      </div>
                      {materials.map((m, i) => {
                        const isVerified = m.verification === 'verified'
                        return (
                          <div key={i} className="mt__r">
                            <span className="font-body-base" style={{ flex: 2, color: 'var(--on-surface)' }}>{m.item}</span>
                            <span className="font-data-mono" style={{ flex: 1, color: 'var(--on-surface)' }}>{m.catalog_number}</span>
                            <span className="font-body-base" style={{ flex: 1, color: 'var(--on-surface-variant)' }}>{m.supplier}</span>
                            <span className="font-data-mono" style={{ flex: .5, textAlign: 'right', color: 'var(--on-surface-variant)' }}>{m.quantity}</span>
                            <span className="font-data-mono" style={{ flex: .5, textAlign: 'right', color: 'var(--on-surface)' }}>{formatMoney(m.total_price, m.currency || budgetCurrency)}</span>
                            <span style={{ flex: .8, textAlign: 'center' }}>
                              {!isVerified && (
                                <span className="mt__u font-label-caps">
                                  <span className="material-symbols-outlined" style={{ fontSize: 12 }}>warning</span>
                                  Verify
                                </span>
                              )}
                              {isVerified && (
                                <span className="mt__v font-label-caps">
                                  <span className="material-symbols-outlined" style={{ fontSize: 12 }}>check_circle</span>
                                  Verified
                                </span>
                              )}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </>
                )}
              </div>
            )}

            {at === 'budget' && (
              <div className="ed__tc animate-fadeIn">
                <div className="bp">
                  <div className="bp__sum">
                    <span className="font-label-caps" style={{ color: 'var(--outline)' }}>ESTIMATED TOTAL</span>
                    <span className="font-headline-md" style={{ color: 'var(--on-surface)', fontWeight: 500, letterSpacing: '-0.01em' }}>{formatMoney(budgetTotal, budgetCurrency)}</span>
                  </div>
                  {[
                    { c: 'Reagents', a: budgetBreakdown.reagents },
                    { c: 'Consumables', a: budgetBreakdown.consumables },
                    { c: 'Equipment Usage', a: budgetBreakdown.equipment_usage },
                  ].map((b, i) => (
                    <div key={i} className="bp__row">
                      <div><span className="font-body-base" style={{ color: 'var(--on-surface)' }}>{b.c}</span></div>
                      <span className="font-data-mono" style={{ color: 'var(--on-surface)' }}>{formatMoney(Number(b.a ?? 0), budgetCurrency)}</span>
                    </div>
                  ))}
                  {currentPlan.budget.notes && (
                    <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', fontSize: 12, marginTop: 12 }}>{currentPlan.budget.notes}</p>
                  )}
                </div>
              </div>
            )}

            {at === 'timeline' && (
              <div className="ed__tc animate-fadeIn">
                <div className="tp">
                  {(currentPlan.timeline.phases ?? []).length === 0 ? (
                    <div className="font-body-base" style={{ padding: 24, color: 'var(--on-surface-variant)', textAlign: 'center' }}>
                      Keine Timeline vorhanden.
                    </div>
                  ) : (
                    currentPlan.timeline.phases.map((t, i, a) => (
                      <div key={i} className="tp__phase">
                        <div className="tp__marker">
                          <div className="tp__dot" />
                          {i < a.length - 1 && <div className="tp__line" />}
                        </div>
                        <div className="tp__content">
                          <div className="tp__hdr">
                            <h4 className="font-body-base" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>{t.phase}</h4>
                            <span className="font-data-mono" style={{ color: 'var(--on-surface-variant)', fontSize: 12 }}>{t.duration}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                            <span className="font-label-caps" style={{ color: 'var(--outline)' }}>Tasks: {t.tasks.length}</span>
                            <span className="font-label-caps" style={{ color: 'var(--outline)' }}>Depends: {t.dependencies.length ? t.dependencies.join(', ') : 'None'}</span>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {at === 'validation' && (
              <div className="ed__tc animate-fadeIn">
                <div className="vp" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                  <section>
                    <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 8 }}>SUCCESS CRITERIA</div>
                    {validation && validation.success_criteria.length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {validation.success_criteria.map((sc, i) => (
                          <li key={i} className="font-body-base" style={{ color: 'var(--on-surface)' }}>{sc}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>Keine Success Criteria definiert.</p>
                    )}
                  </section>

                  <section>
                    <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 8 }}>CONTROLS</div>
                    {validation && validation.controls.length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {validation.controls.map((c, i) => (
                          <li key={i} className="font-body-base" style={{ color: 'var(--on-surface)' }}>{c}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>Keine Kontrollen definiert.</p>
                    )}
                  </section>

                  <section>
                    <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 8 }}>STATISTICAL PLAN</div>
                    <p className="font-body-base" style={{ color: 'var(--on-surface)' }}>
                      {validation?.statistical_plan || 'Kein statistischer Plan vorhanden.'}
                    </p>
                  </section>

                  <section>
                    <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 8 }}>REVIEW ISSUES</div>
                    {reviewIssues.length === 0 ? (
                      <div className="vp__item vp__item--pass">
                        <span className="material-symbols-outlined" style={{ color: 'var(--on-surface-variant)', fontSize: 20 }}>check_circle</span>
                        <div>
                          <span className="font-body-base" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Keine Issues</span>
                          <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', fontSize: 13 }}>Review Agent hat keine Probleme markiert.</p>
                        </div>
                      </div>
                    ) : (
                      reviewIssues.map((issue, i) => {
                        const isError = issue.severity === 'error'
                        return (
                          <div key={i} className={`vp__item vp__item--${isError ? 'warn' : 'pass'}`}>
                            <span className="material-symbols-outlined" style={{ color: isError ? 'var(--tertiary)' : 'var(--on-surface-variant)', fontSize: 20 }}>{isError ? 'warning' : 'info'}</span>
                            <div>
                              <span className="font-body-base" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>{issue.path || issue.severity.toUpperCase()}</span>
                              <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', fontSize: 13 }}>{issue.message}</p>
                            </div>
                          </div>
                        )
                      })
                    )}
                  </section>
                </div>
              </div>
            )}

            {at === 'literature' && (
              <div className="ed__tc animate-fadeIn">
                <div className="lp">
                  {literature.length === 0 ? (
                    <div className="lp__item">
                      <div className="lp__tag font-label-caps">{noveltyLabel(currentPlan.literature_qc.novelty_signal)}</div>
                      <h4 className="font-body-base" style={{ fontWeight: 500, color: 'var(--on-surface)', marginBottom: 4 }}>No references found</h4>
                      <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', fontSize: 12, marginTop: 8 }}>
                        {currentPlan.literature_qc.summary || 'Literature Scout konnte keine direkten Treffer liefern.'}
                      </p>
                    </div>
                  ) : (
                    literature.map((l, i) => {
                      const refLine = [l.authors, l.journal, l.year].filter(Boolean).join(', ')
                      const detail = l.key_difference || l.similarity || 'Reference from literature scout.'
                      return (
                        <div key={i} className="lp__item">
                          <div className="lp__tag font-label-caps">{noveltyLabel(currentPlan.literature_qc.novelty_signal)}</div>
                          <h4 className="font-body-base" style={{ fontWeight: 500, color: 'var(--on-surface)', marginBottom: 4 }}>{l.title}</h4>
                          {refLine && <p className="font-data-mono" style={{ color: 'var(--on-surface-variant)', fontSize: 11 }}>{refLine}</p>}
                          <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', fontSize: 12, marginTop: 8 }}>{detail}</p>
                          {l.url && (
                            <a href={l.url} target="_blank" rel="noopener noreferrer" className="font-label-caps" style={{ marginTop: 8, color: 'var(--primary)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>open_in_new</span>
                              Open
                            </a>
                          )}
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="ed__side">
            <div className="ed__insight animate-slideInRight" id="literature-summary">
              <div className="ed__insight-glow" />
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--on-surface-variant)' }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>auto_stories</span>
                  <span className="font-label-caps">LITERATURE QC</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="ed__badge font-label-caps" style={{ background: 'color-mix(in srgb, var(--primary) 14%, transparent)', color: 'var(--primary)' }}>
                    {noveltyLabel(currentPlan.literature_qc.novelty_signal)}
                  </span>
                  <span className="font-data-mono" style={{ color: 'var(--on-surface-variant)', fontSize: 11 }}>
                    {literature.length} REFS
                  </span>
                </div>
                <p className="font-body-base" style={{ color: 'var(--on-surface)' }}>
                  {currentPlan.literature_qc.summary || 'No literature summary available.'}
                </p>
              </div>
            </div>

            <div className="ed__meta animate-slideInRight" style={{ animationDelay: '0.1s' }} id="experiment-metadata">
              <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 12 }}>EXPERIMENT METADATA</div>
              {[
                ['Plan ID', currentPlan.plan_id],
                ['Experiment Type', experimentType],
                ['Generated By', generatedBy],
                ['Generated At', generatedAt],
                ['Knowledge Nodes', String(knowledgeNodeCount)],
                ['Status', badgeLabel],
              ].map(([l, v], i, arr) => (
                <div
                  key={l}
                  className="ed__meta-row"
                  style={i === arr.length - 1 ? { borderBottom: 'none' } : undefined}
                >
                  <span className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>{l}</span>
                  <span className="font-data-mono" style={{ color: 'var(--on-surface)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={v}>{v}</span>
                </div>
              ))}
            </div>

            {candidateSummary && Object.keys(candidateSummary).length > 0 && (
              <div className="ed__meta animate-slideInRight" style={{ animationDelay: '0.2s' }} id="candidate-summary">
                <div className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 12 }}>KNOWLEDGE CANDIDATES</div>
                {Object.entries(candidateSummary).map(([key, count], i, arr) => (
                  <div
                    key={key}
                    className="ed__meta-row"
                    style={i === arr.length - 1 ? { borderBottom: 'none' } : undefined}
                  >
                    <span className="font-body-base" style={{ color: 'var(--on-surface-variant)', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                    <span className="font-data-mono" style={{ color: 'var(--on-surface)' }}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
