import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { listRecentPlans } from '../../lib/api'
import type { ExperimentSummary } from '../../types/plan'
import './Sidebar.css'

interface NavItem { icon: string; label: string; path: string; }

const mainNav: NavItem[] = [
  { icon: 'dashboard', label: 'Dashboard', path: '/' },
  { icon: 'science', label: 'Lab Notebook', path: '/lab-notebook' },
  { icon: 'hub', label: 'Agent Network', path: '/agent-network' },
  { icon: 'schema', label: 'Knowledge Graph', path: '/knowledge-garden' },
]

const formatRelative = (iso: string): string => {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

export default function Sidebar({ isOpen }: { isOpen: boolean }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [plans, setPlans] = useState<ExperimentSummary[]>([])

  const refreshPlans = async (): Promise<void> => {
    try {
      const list = await listRecentPlans()
      setPlans(list.slice(0, 5))
    } catch {
      setPlans([])
    }
  }

  useEffect(() => {
    void refreshPlans()
    const t = setInterval(() => void refreshPlans(), 15000)
    return () => clearInterval(t)
  }, [location.pathname])

  const isActive = (path: string) => {
    const pathname = location.pathname
    if (path === '/') {
      return pathname === '/' || pathname === '/experiments'
    }
    if (path === '/lab-notebook') {
      return pathname === '/lab-notebook' || (pathname.startsWith('/experiments/') && !pathname.endsWith('/progress'))
    }
    if (path === '/agent-network') {
      return pathname === '/agent-network' || pathname.endsWith('/progress')
    }
    return pathname === path
  }

  const isPlanActive = (planId: string): boolean => {
    return location.pathname === `/experiments/${planId}`
  }

  return (
    <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`} id="sidebar-nav" aria-hidden={!isOpen}>
      <div className="sidebar__session">
        <div className="sidebar__session-header">
          <div className="sidebar__session-icon">
            <span className="material-symbols-outlined" style={{ fontSize: 20, color: 'var(--on-surface-variant)' }}>science</span>
          </div>
          <div>
            <h2 className="sidebar__session-name">Dr. Nexus</h2>
            <p className="sidebar__session-time font-data-mono">MULTI-AGENT LAB</p>
          </div>
        </div>
      </div>
      <nav className="sidebar__nav">
        {mainNav.map((item) => (
          <button
            type="button"
            key={item.label}
            className={`sidebar__nav-item ${isActive(item.path) ? 'sidebar__nav-item--active' : ''}`}
            onClick={() => navigate(item.path)}
            aria-current={isActive(item.path) ? 'page' : undefined}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20, fontVariationSettings: isActive(item.path) ? "'FILL' 1" : "'FILL' 0" }}>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      {plans.length > 0 && (
        <div
          className="sidebar__plans"
          id="sidebar-recent-plans"
          aria-label="Recent experiment plans"
        >
          <div
            className="sidebar__plans-head"
            title="Saved experiment plans from completed agent runs"
          >
            <span className="font-label-caps">RECENT EXPERIMENTS</span>
            <span className="font-data-mono sidebar__plans-count">{plans.length}</span>
          </div>
          <div className="sidebar__plans-list">
            {plans.map((plan) => (
              <button
                key={plan.plan_id}
                type="button"
                className={`sidebar__plan-item ${isPlanActive(plan.plan_id) ? 'sidebar__plan-item--active' : ''}`}
                onClick={() => navigate(`/experiments/${plan.plan_id}`)}
                title={`${plan.hypothesis}\n\nPlan ID: ${plan.plan_id}`}
              >
                <span className="material-symbols-outlined sidebar__plan-icon">description</span>
                <span className="sidebar__plan-text">
                  <span className="sidebar__plan-title">{plan.title}</span>
                  <span className="sidebar__plan-meta font-data-mono">{formatRelative(plan.generated_at)}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
