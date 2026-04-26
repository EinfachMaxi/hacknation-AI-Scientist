import { Navigate, useNavigate } from 'react-router-dom'
import { getActiveRunId, getLatestPlanId } from '../../lib/api'
import '../LabNotebook/LabNotebook.css'

export default function AgentNetwork() {
  const navigate = useNavigate()
  const activeRunId = getActiveRunId()
  const latestPlanId = getLatestPlanId()

  if (activeRunId) {
    return <Navigate to={`/experiments/${activeRunId}/progress`} replace />
  }

  return (
    <div className="lab-empty">
      <div className="lab-empty__container">
        <section className="lab-empty__panel animate-fadeIn">
          <div className="lab-empty__icon-wrapper">
            <span className="material-symbols-outlined lab-empty__icon">hub</span>
          </div>
          <span className="lab-empty__eyebrow font-label-caps">Agent Network</span>
          <h1 className="font-headline-md lab-empty__title">No active research run</h1>
          <p className="lab-empty__subtitle">
            The agent network only comes alive while a research run is in progress. Start a new
            hypothesis on the dashboard to spin up the swarm, or revisit a finished plan in your lab
            notebook.
          </p>
          <div className="lab-empty__actions">
            <button
              type="button"
              className="lab-empty__primary-btn font-label-caps"
              onClick={() => navigate('/')}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>biotech</span>
              Start a New Research Run
            </button>
            {latestPlanId ? (
              <button
                type="button"
                className="lab-empty__primary-btn font-label-caps"
                style={{ background: 'var(--surface-container-low)', color: 'var(--on-surface)', border: '1px solid var(--outline-variant)', marginLeft: 12 }}
                onClick={() => navigate('/lab-notebook')}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>science</span>
                Open Lab Notebook
              </button>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  )
}
