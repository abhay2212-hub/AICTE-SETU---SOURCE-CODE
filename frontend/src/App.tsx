// Owner: Dev D
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AictePage from './pages/aicte'
import BlindMatchPage from './pages/blindmatch'
import HomePage from './pages/home'
import InstitutionPage from './pages/institution'
import MapPage from './pages/map'
import StudentPage from './pages/student'
import VerifierPage from './pages/verifier'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="institution/*" element={<InstitutionPage />} />
        <Route path="aicte/*" element={<AictePage />} />
        <Route path="blindmatch/*" element={<BlindMatchPage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="student/*" element={<StudentPage />} />
        <Route path="verifier/*" element={<VerifierPage />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Route>
    </Routes>
  )
}
