import { Navigate, useNavigate } from 'react-router-dom'
import { getActiveRunId, getLatestPlanId } from '../../lib/api'
import './LabNotebook.css'

export default function LabNotebook() {
  const navigate = useNavigate()
  const latestPlanId = getLatestPlanId()
  const activeRunId = getActiveRunId()

  if (latestPlanId) {
    return <Navigate to={`/experiments/${latestPlanId}`} replace />
  }

  const inProgress = Boolean(activeRunId)

  return (
    <div className="lab-empty">
      <div className="lab-empty__container">
        <section className="lab-empty__panel animate-fadeIn">
          <div className="lab-empty__icon-wrapper">
            <span className="material-symbols-outlined lab-empty__icon">science</span>
          </div>
          <span className="lab-empty__eyebrow font-label-caps">Lab Notebook</span>
          <h1 className="font-headline-md lab-empty__title">
            {inProgress ? 'Your first research project is running' : 'Start your first research project'}
          </h1>
          <p className="lab-empty__subtitle">
            {inProgress
              ? 'The agent network is currently working on your hypothesis. Once the experimental plan is generated, it will appear right here in your lab notebook.'
              : 'No experimental plans yet. Describe a scientific hypothesis on the dashboard and the AI agent network will assemble a structured protocol, materials list, budget and timeline for you.'}
          </p>
          <div className="lab-empty__actions">
            {inProgress ? (
              <button
                type="button"
                className="lab-empty__primary-btn font-label-caps"
                onClick={() => navigate(`/experiments/${activeRunId}/progress`)}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>hub</span>
                View Agent Network
              </button>
            ) : (
              <button
                type="button"
                className="lab-empty__primary-btn font-label-caps"
                onClick={() => navigate('/')}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>biotech</span>
                Formulate Hypothesis
              </button>
            )}
          </div>
          <div className="lab-empty__steps">
            <div className="lab-empty__step">
              <span className="lab-empty__step-num font-data-mono">01</span>
              <div>
                <span className="font-label-caps lab-empty__step-label">Hypothesis</span>
                <p>Write a question or hypothesis on the dashboard.</p>
              </div>
            </div>
            <div className="lab-empty__step">
              <span className="lab-empty__step-num font-data-mono">02</span>
              <div>
                <span className="font-label-caps lab-empty__step-label">Agent Network</span>
                <p>Watch specialized agents collaborate in real time.</p>
              </div>
            </div>
            <div className="lab-empty__step">
              <span className="lab-empty__step-num font-data-mono">03</span>
              <div>
                <span className="font-label-caps lab-empty__step-label">Lab Notebook</span>
                <p>Review the generated experimental plan right here.</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
