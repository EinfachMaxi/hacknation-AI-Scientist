import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { setActiveRunId, startRun } from "../../lib/api";
import "./Dashboard.css";

export default function Dashboard() {
  const [hypothesis, setHypothesis] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const navigate = useNavigate();
  const canGenerate = hypothesis.trim().length > 0;

  const handleStartAgents = async (): Promise<void> => {
    if (!canGenerate || isInitializing) {
      return;
    }

    const prompt = hypothesis.trim();
    if (!prompt) {
      return;
    }

    setStartError(null);
    setIsInitializing(true);

    try {
      const run = await startRun({
        prompt,
        use_mock: false,
      });
      setActiveRunId(run.run_id);
      navigate(`/experiments/${run.run_id}/progress`, {
        state: {
          hypothesis: prompt,
          runId: run.run_id,
        },
      });
    } catch (error) {
      setStartError(
        error instanceof Error ? error.message : "Could not start run",
      );
      setIsInitializing(false);
    }
  };

  return (
    <div className="dashboard knowledge-grid">
      <div className="dashboard__container">
        <section
          className="dashboard__input-section animate-fadeIn"
          id="hypothesis-input-section"
        >
          <div className="dashboard__input-glow"></div>
          <h1 className="font-headline-md dashboard__title">
            <span className="material-symbols-outlined dashboard__title-icon">
              biotech
            </span>
            Scientific Question Formulation
          </h1>
          <p className="dashboard__subtitle">
            Describe a hypothesis or research question. The agent network will
            generate a structured experimental plan with protocol, materials,
            budget and timeline.
          </p>
          <div className="dashboard__textarea-wrapper">
            <label className="dashboard__sr-only" htmlFor="hypothesis-textarea">
              Scientific hypothesis input
            </label>
            <textarea
              className="dashboard__textarea font-data-mono"
              placeholder="Type your hypothesis (e.g., A paper-based electrochemical biosensor...)"
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              id="hypothesis-textarea"
              aria-describedby="hypothesis-status"
            />
            <div
              className="dashboard__textarea-status font-label-caps"
              id="hypothesis-status"
              aria-live="polite"
            >
              {hypothesis.length > 0
                ? `${hypothesis.length} CHARS`
                : "AWAITING INPUT"}
            </div>
          </div>
          <div className="dashboard__input-actions">
            {isInitializing ? (
              <div
                className="dashboard__init-box"
                role="status"
                aria-live="polite"
              >
                <div className="dashboard__init-row">
                  <span className="material-symbols-outlined dashboard__init-gear">
                    settings
                  </span>
                  <span className="font-label-caps">Initialize...</span>
                </div>
                <div
                  className="dashboard__init-progress-track"
                  aria-hidden="true"
                >
                  <div className="dashboard__init-progress-fill"></div>
                </div>
              </div>
            ) : (
              <button
                className="dashboard__generate-btn btn-glow font-label-caps"
                onClick={() => void handleStartAgents()}
                id="generate-plan-btn"
                disabled={!canGenerate}
                aria-disabled={!canGenerate}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: 16 }}
                >
                  hub
                </span>
                Start Agents Network
              </button>
            )}
            {startError ? (
              <p className="dashboard__start-error" role="alert">
                {startError}
              </p>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
