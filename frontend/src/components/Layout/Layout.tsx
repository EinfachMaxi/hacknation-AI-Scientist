import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import TopAppBar from '../TopAppBar/TopAppBar'
import Sidebar from '../Sidebar/Sidebar'
import './Layout.css'

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="layout">
      <TopAppBar sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((prev) => !prev)} />
      <Sidebar isOpen={sidebarOpen} />
      <main className={`layout__main ${sidebarOpen ? 'layout__main--with-sidebar' : ''}`}>
        <Outlet />
      </main>
    </div>
  )
}
