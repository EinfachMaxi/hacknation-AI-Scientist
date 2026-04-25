import { useNavigate, useLocation } from 'react-router-dom'
import './TopAppBar.css'

const navLinks = [
  { label: 'Experiments', path: '/' },
  { label: 'Agents', path: '/agents' },
]

interface TopAppBarProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
}

export default function TopAppBar({ sidebarOpen, onToggleSidebar }: TopAppBarProps) {
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/agents') return location.pathname === '/agents'
    if (path === '/') return location.pathname === '/' || location.pathname.startsWith('/experiments')
    return location.pathname.startsWith(path)
  }

  return (
    <header className="topbar" id="top-app-bar">
      <div className="topbar__left">
        <button
          type="button"
          className="topbar__menu-btn"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          aria-expanded={sidebarOpen}
          aria-controls="sidebar-nav"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 22 }}>
            {sidebarOpen ? 'menu_open' : 'menu'}
          </span>
        </button>
        <button type="button" className="topbar__logo" onClick={() => navigate('/')} aria-label="Go to dashboard">
          The AI Scientist
        </button>
        <nav className="topbar__nav">
          {navLinks.map((link) => (
            <button
              type="button"
              key={link.label}
              className={`topbar__nav-link ${isActive(link.path) ? 'topbar__nav-link--active' : ''}`}
              onClick={() => navigate(link.path)}
              aria-current={isActive(link.path) ? 'page' : undefined}
            >
              {link.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="topbar__right">
        <div className="topbar__search">
          <span className="material-symbols-outlined topbar__search-icon">search</span>
          <input className="topbar__search-input font-data-mono" placeholder="Search experiments..." type="text" id="global-search" />
        </div>
        <button className="topbar__new-btn btn-glow" id="new-experiment-btn" onClick={() => navigate('/')}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add</span>
          New Experiment
        </button>
        <div className="topbar__actions">
          <button className="topbar__icon-btn" aria-label="Settings">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>settings</span>
          </button>
          <button className="topbar__icon-btn topbar__icon-btn--notif" aria-label="Notifications">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>notifications</span>
            <span className="topbar__notif-dot"></span>
          </button>
        </div>
        <div className="topbar__avatar" id="user-avatar">
          <span className="material-symbols-outlined" style={{ fontSize: 20, color: 'var(--on-surface-variant)' }}>person</span>
        </div>
      </div>
    </header>
  )
}
