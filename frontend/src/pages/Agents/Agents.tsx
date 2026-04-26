import { useEffect, useState } from "react";
import { fetchBackendAgents } from "../../lib/api";
import type { BackendAgent } from "../../types/plan";
import "./Agents.css";

const ICON_MAP: Record<string, string> = {
  planner: "hub",
  literature: "menu_book",
  protocol: "architecture",
  materials: "science",
  budget: "payments",
  timeline: "calendar_month",
  review: "fact_check",
  validation: "verified",
};

const fallbackIcon = "smart_toy";

const formatToolList = (metadata: Record<string, unknown>): string[] => {
  const allowed = metadata?.allowed_tools;
  if (Array.isArray(allowed)) {
    return allowed.filter((t): t is string => typeof t === "string");
  }
  return [];
};

const formatDomains = (metadata: Record<string, unknown>): string[] => {
  const include = metadata?.include_domains;
  if (Array.isArray(include)) {
    return include.filter((t): t is string => typeof t === "string");
  }
  return [];
};

export default function Agents() {
  const [agents, setAgents] = useState<BackendAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadAgents = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchBackendAgents();
      setAgents(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAgents();
  }, []);

  return (
    <div className="agents-page knowledge-grid">
      <div className="agents-page__container">
        <section className="agents-page__panel animate-fadeIn">
          <div className="agents-page__head">
            <div>
              <h1 className="font-headline-md agents-page__title">
                <span className="material-symbols-outlined">hub</span>
                Available Agents
              </h1>
              <p className="agents-page__subtitle">
                These agents power Dr. Nexus's multi-agent workflows. The list is
                served live from the backend registry (Supabase
                <code> agents </code> table).
              </p>
            </div>
            <button
              type="button"
              className="agents-page__refresh"
              onClick={() => void loadAgents()}
              disabled={loading}
              aria-label="Refresh agent list"
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: 18 }}
              >
                {loading ? "hourglass_top" : "refresh"}
              </span>
              <span className="font-label-caps">
                {loading ? "LOADING" : "REFRESH"}
              </span>
            </button>
          </div>

          {error && (
            <div className="agents-page__error" role="alert">
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                error
              </span>
              <span className="font-body-base">{error}</span>
            </div>
          )}

          {loading && !agents && (
            <div className="agents-page__loading">
              <span className="material-symbols-outlined" style={{ fontSize: 32 }}>
                hourglass_top
              </span>
              <p className="font-body-base">Loading agent registry…</p>
            </div>
          )}

          {agents && agents.length === 0 && !loading && (
            <div className="agents-page__loading">
              <span
                className="material-symbols-outlined"
                style={{ fontSize: 32, color: "var(--outline)" }}
              >
                inbox
              </span>
              <p className="font-body-base">No active agents registered.</p>
            </div>
          )}

          {agents && agents.length > 0 && (
            <div className="agents-page__grid">
              {agents.map((agent) => {
                const icon = ICON_MAP[agent.key] ?? fallbackIcon;
                const tools = formatToolList(agent.metadata);
                const domains = formatDomains(agent.metadata);
                return (
                  <article
                    key={agent.key}
                    className="agents-page__card"
                    id={`agent-card-${agent.key}`}
                  >
                    <div className="agents-page__card-header">
                      <span className="material-symbols-outlined">{icon}</span>
                      <h2>{agent.name}</h2>
                      <span
                        className={`agents-page__badge agents-page__badge--${
                          agent.is_active ? "active" : "inactive"
                        }`}
                      >
                        {agent.is_active ? "ACTIVE" : "DISABLED"}
                      </span>
                    </div>
                    <p className="agents-page__role">{agent.role}</p>
                    {agent.personality && (
                      <p className="agents-page__personality">
                        <span className="font-label-caps">PERSONALITY · </span>
                        {agent.personality}
                      </p>
                    )}

                    {agent.capabilities.length > 0 && (
                      <div className="agents-page__chips">
                        {agent.capabilities.map((cap) => (
                          <span
                            key={cap}
                            className="agents-page__chip font-data-mono"
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    )}

                    {(tools.length > 0 || domains.length > 0) && (
                      <div className="agents-page__meta">
                        {tools.length > 0 && (
                          <div className="agents-page__meta-row">
                            <span className="font-label-caps">TOOLS</span>
                            <span className="font-data-mono">
                              {tools.join(" · ")}
                            </span>
                          </div>
                        )}
                        {domains.length > 0 && (
                          <div className="agents-page__meta-row">
                            <span className="font-label-caps">DOMAINS</span>
                            <span className="font-data-mono">
                              {domains.slice(0, 3).join(", ")}
                              {domains.length > 3 ? `, +${domains.length - 3}` : ""}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
