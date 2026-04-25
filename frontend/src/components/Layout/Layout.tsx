import { Outlet } from 'react-router-dom'
import TopAppBar from '../TopAppBar/TopAppBar'
import Sidebar from '../Sidebar/Sidebar'
import './Layout.css'

export default function Layout() {
  return (
    <div className="layout">
      <TopAppBar />
      <Sidebar />
      <main className="layout__main">
        <Outlet />
      </main>
    </div>
  )
}
