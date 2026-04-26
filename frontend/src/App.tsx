import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout/Layout'
import Dashboard from './pages/Dashboard/Dashboard'
import Agents from './pages/Agents/Agents'
import LiveAgentProgress from './pages/LiveAgentProgress/LiveAgentProgress'
import ExperimentPlanDetail from './pages/ExperimentPlanDetail/ExperimentPlanDetail'
import KnowledgeGarden from './pages/KnowledgeGarden/KnowledgeGarden'
import LabNotebook from './pages/LabNotebook/LabNotebook'
import AgentNetwork from './pages/AgentNetwork/AgentNetwork'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/experiments" element={<Dashboard />} />
        <Route path="/experiments/:id/progress" element={<LiveAgentProgress />} />
        <Route path="/experiments/:id" element={<ExperimentPlanDetail />} />
        <Route path="/lab-notebook" element={<LabNotebook />} />
        <Route path="/agent-network" element={<AgentNetwork />} />
        <Route path="/knowledge-garden" element={<KnowledgeGarden />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
