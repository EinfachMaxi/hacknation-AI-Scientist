import './Agents.css'

const availableAgents = [
  {
    id: 'literature',
    name: 'Literature Scout',
    role: 'Findet relevante Paper, Methoden und Benchmark-Ergebnisse.',
    icon: 'menu_book',
  },
  {
    id: 'protocol',
    name: 'Protocol Designer',
    role: 'Baut aus Erkenntnissen ein strukturiertes Experiment-Protokoll.',
    icon: 'architecture',
  },
  {
    id: 'materials',
    name: 'Materials Agent',
    role: 'Ermittelt Reagenzien, Verfuegbarkeit und Bezugsquellen.',
    icon: 'science',
  },
  {
    id: 'validation',
    name: 'Validation Agent',
    role: 'Prueft Konsistenz, Risiken und Qualitaet des Plans.',
    icon: 'fact_check',
  },
]

export default function Agents() {
  return (
    <div className="agents-page knowledge-grid">
      <div className="agents-page__container">
        <section className="agents-page__panel glass-panel animate-fadeIn">
          <h1 className="font-headline-md agents-page__title">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>hub</span>
            Available Agents
          </h1>
          <p className="agents-page__subtitle">
            Diese Agents stehen im Multi Agent Network fuer deine Scientific Workflows bereit.
          </p>
          <div className="agents-page__grid">
            {availableAgents.map((agent) => (
              <article key={agent.id} className="agents-page__card">
                <div className="agents-page__card-header">
                  <span className="material-symbols-outlined">{agent.icon}</span>
                  <h2>{agent.name}</h2>
                </div>
                <p>{agent.role}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
