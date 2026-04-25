import { useNavigate, useLocation } from 'react-router-dom'
import './Sidebar.css'

interface NavItem { icon: string; label: string; path: string; }

const mainNav: NavItem[] = [
  { icon: 'dashboard', label: 'Dashboard', path: '/' },
  { icon: 'science', label: 'Lab Notebook', path: '/experiments/EXP-8492' },
  { icon: 'hub', label: 'Agent Network', path: '#' },
  { icon: 'schema', label: 'Knowledge Graph', path: '/knowledge-garden' },
]

export default function Sidebar({ isOpen }: { isOpen: boolean }) {
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || (location.pathname.startsWith('/experiments') && !location.pathname.includes('EXP'))
    if (path === '/experiments/EXP-8492') return location.pathname.includes('/experiments/') && location.pathname.includes('EXP')
    return location.pathname === path
  }

  return (
    <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`} id="sidebar-nav" aria-hidden={!isOpen}>
      <div className="sidebar__session">
        <div className="sidebar__session-header">
          <div className="sidebar__session-icon">
            <span className="material-symbols-outlined" style={{ color: 'var(--primary)', fontVariationSettings: "'FILL' 1" }}>science</span>
          </div>
          <div>
            <h2 className="sidebar__session-name">Lab Alpha-7</h2>
            <p className="sidebar__session-time font-data-mono">Active Session: 04:12:00</p>
          </div>
        </div>
      </div>
      <nav className="sidebar__nav">
        {mainNav.map((item) => (
          <button
            type="button"
            key={item.label}
            className={`sidebar__nav-item ${isActive(item.path) ? 'sidebar__nav-item--active' : ''}`}
            onClick={() => { if (item.path !== '#') navigate(item.path) }}
            aria-current={isActive(item.path) ? 'page' : undefined}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20, fontVariationSettings: isActive(item.path) ? "'FILL' 1" : "'FILL' 0" }}>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}
