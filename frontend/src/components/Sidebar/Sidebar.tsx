import { useNavigate, useLocation } from 'react-router-dom'
import './Sidebar.css'

interface NavItem { icon: string; label: string; path: string; }

const mainNav: NavItem[] = [
  { icon: 'dashboard', label: 'Dashboard', path: '/' },
  { icon: 'science', label: 'Lab Notebook', path: '/experiments/EXP-8492' },
  { icon: 'hub', label: 'Agent Network', path: '#' },
  { icon: 'schema', label: 'Knowledge Graph', path: '/knowledge-garden' },
  { icon: 'inventory_2', label: 'Archive', path: '#' },
]

const bottomNav: NavItem[] = [
  { icon: 'memory', label: 'System Status', path: '#' },
  { icon: 'help_outline', label: 'Documentation', path: '#' },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/' || (location.pathname.startsWith('/experiments') && !location.pathname.includes('EXP'))
    if (path === '/experiments/EXP-8492') return location.pathname.includes('/experiments/') && location.pathname.includes('EXP')
    return location.pathname === path
  }

  return (
    <aside className="sidebar" id="sidebar-nav">
      <div className="sidebar__session">
        <div className="sidebar__session-header">
          <div className="sidebar__session-icon">
            <span className="material-symbols-outlined" style={{ color: '#60a5fa', fontVariationSettings: "'FILL' 1" }}>science</span>
          </div>
          <div>
            <h2 className="sidebar__session-name">Lab Alpha-7</h2>
            <p className="sidebar__session-time font-data-mono">Active Session: 04:12:00</p>
          </div>
        </div>
      </div>
      <nav className="sidebar__nav">
        {mainNav.map((item) => (
          <a key={item.label} className={`sidebar__nav-item ${isActive(item.path) ? 'sidebar__nav-item--active' : ''}`}
            onClick={(e) => { e.preventDefault(); if (item.path !== '#') navigate(item.path) }} href={item.path}>
            <span className="material-symbols-outlined" style={{ fontSize: 20, fontVariationSettings: isActive(item.path) ? "'FILL' 1" : "'FILL' 0" }}>{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </nav>
      <div className="sidebar__bottom">
        {bottomNav.map((item) => (
          <a key={item.label} className="sidebar__nav-item" onClick={(e) => { e.preventDefault() }} href={item.path}>
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </div>
    </aside>
  )
}
