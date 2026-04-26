import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startRun } from '../../lib/api'
import './Dashboard.css'

export default function Dashboard() {
  const [hypothesis, setHypothesis] = useState('')
  const navigate = useNavigate()
  const canGenerate = hypothesis.trim().length > 0

  return (
    <div className="dashboard knowledge-grid">
      <div className="dashboard__container">
        <section className="dashboard__input-section glass-panel animate-fadeIn" id="hypothesis-input-section">
          <div className="dashboard__input-glow"></div>
          <h1 className="font-headline-md dashboard__title">
            <span className="material-symbols-outlined dashboard__title-icon" style={{ fontVariationSettings: "'FILL' 1" }}>biotech</span>
            Scientific Question Formulation
          </h1>
          <div className="dashboard__textarea-wrapper">
            <label className="dashboard__sr-only" htmlFor="hypothesis-textarea">Scientific hypothesis input</label>
            <textarea
              className="dashboard__textarea font-data-mono"
              placeholder="Type your hypothesis (e.g., A paper-based electrochemical biosensor...)"
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              id="hypothesis-textarea"
              aria-describedby="hypothesis-status"
            />
            <div className="dashboard__textarea-status font-label-caps" id="hypothesis-status" aria-live="polite">
              {hypothesis.length > 0 ? `${hypothesis.length} CHARS` : 'AWAITING INPUT'}
            </div>
          </div>
          <div className="dashboard__input-actions">
            <button
              className="dashboard__generate-btn btn-glow font-label-caps"
              onClick={async () => {
                if (canGenerate) {
                  const run = await startRun({
                    prompt: hypothesis.trim(),
                    use_mock: false,
                  })
                  navigate(`/experiments/${run.run_id}/progress`, {
                    state: {
                      hypothesis: hypothesis.trim(),
                      runId: run.run_id,
                    },
                  })
                }
              }}
              id="generate-plan-btn"
              disabled={!canGenerate}
              aria-disabled={!canGenerate}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>hub</span>Start Agents Network
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}
