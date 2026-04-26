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
          Dr. Nexus
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
        <button className="topbar__new-btn btn-glow" id="new-experiment-btn" onClick={() => navigate('/')}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add</span>
          New Experiment
        </button>
        <button
          type="button"
          className="topbar__icon-btn"
          aria-label="Open Knowledge Garden"
          onClick={() => navigate('/knowledge-garden')}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>account_tree</span>
        </button>
      </div>
    </header>
  )
}
