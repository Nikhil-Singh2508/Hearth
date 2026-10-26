import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { authApi, type AuthUser } from './lib/api'
import LoginPage from './pages/LoginPage'
import PropertiesPage from './pages/PropertiesPage'
import TenantPortalPage from './pages/TenantPortalPage'
import MaintenancePage from './pages/MaintenancePage'
import TenantsPage from './pages/TenantsPage'
import AcceptInvitationPage from './pages/AcceptInvitationPage'
import AgreementsPage from './pages/AgreementsPage'
import LedgerPage from './pages/LedgerPage'
import DepositsPage from './pages/DepositsPage'
import UtilitiesPage from './pages/UtilitiesPage'
import InspectionsPage from './pages/InspectionsPage'
import DashboardPage from './pages/DashboardPage'
import ReportsPage from './pages/ReportsPage'
import HelpPage from './pages/HelpPage'

const nav = [
  ['Overview', '⌂', '/'], ['Properties', '▦', '/properties'], ['Tenants', '♙', '/tenants'],
  ['Rent & payments', '↗', '/ledger'], ['Security deposits', '₹', '/deposits'], ['Utilities', '⌁', '/utilities'], ['Maintenance', '⚒', '/maintenance'],
]

function App() {
  const [period, setPeriod] = useState('this_month')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()
  useEffect(() => { authApi.current().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false)) }, [])
  useEffect(() => { setMobileNavOpen(false) }, [location.pathname])
  const signOut = () => { void authApi.logout().finally(() => setUser(null)) }
  if (location.pathname === '/accept-invitation') return <AcceptInvitationPage />
  if (loading) return <div className="app-loading" role="status">Checking your session…</div>
  if (!user) return <LoginPage onLogin={setUser} />
  if (user.role === 'tenant') return location.pathname === '/help'
    ? <HelpPage tenant onSignOut={signOut} />
    : <TenantPortalPage onSignOut={signOut} />
  const initials = user.email.slice(0, 2).toUpperCase()
  const page = location.pathname === '/help' ? 'Help guide' : location.pathname === '/properties' ? 'Properties' : location.pathname === '/reports' ? 'Reports & exports' : location.pathname === '/inspections' ? 'Inspections' : location.pathname === '/maintenance' ? 'Maintenance' : location.pathname === '/utilities' ? 'Utilities & expenses' : location.pathname === '/tenants' ? 'Tenants' : location.pathname === '/agreements' ? 'Agreements' : location.pathname === '/ledger' ? 'Rent & payments' : location.pathname === '/deposits' ? 'Security deposits' : location.pathname === '/' ? 'Overview' : 'Coming soon'
  return <div className="shell">
    {mobileNavOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
    <aside className={`sidebar ${mobileNavOpen ? 'is-open' : ''}`}>
      <button className="mobile-nav-close" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}>×</button>
      <a className="brand" href="/"><span className="brand-icon">h</span><span>hearth<small>PROPERTY CARE</small></span></a>
      <div className="workspace"><div className="workspace-mark">R</div><span><b>Rental workspace</b><small>Owner workspace</small></span><span className="chevron">⌄</span></div>
      <div className="nav-label">WORKSPACE</div>
      <nav>{nav.map(([label, icon, path]) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMobileNavOpen(false)} className={({isActive})=>`nav-item ${isActive?'active':''}`}><span className="nav-icon">{icon}</span>{label}{label==='Maintenance'&&<i className="nav-count">3</i>}</NavLink>)}</nav>
      <div className="nav-label tools-label">MANAGE</div>
      <nav>{[['Agreements','▤','/agreements'],['Inspections','☷','/inspections'],['Reports','▥','/reports'],['Help guide','?','/help']].map(([label,icon,path])=><NavLink key={path} to={path} onClick={() => setMobileNavOpen(false)} className={({isActive})=>`nav-item ${isActive?'active':''}`}><span className="nav-icon">{icon}</span>{label}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="help-card"><div className="help-icon">✳</div><b>Need a hand?</b><p>Find setup and workflow instructions.</p><NavLink className="help-link" to="/help">Open help guide <span>↗</span></NavLink></div><div className="profile"><div className="avatar">{initials}</div><span><b>{user.email}</b><small>Property owner</small></span><button className="signout" onClick={signOut}>Sign out</button></div></div>
    </aside>
    <main className="main"><header className="topbar"><button className="mobile-nav-toggle" aria-label="Open navigation" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)}>☰</button><div className="breadcrumbs">Workspace <span>/</span> <b>{page}</b></div><div className="top-actions"><div className="top-avatar">{initials}</div><button className="topbar-signout" onClick={signOut}>Sign out</button></div></header>
      <Routes><Route path="/" element={<DashboardPage period={period} setPeriod={setPeriod}/>} /><Route path="/help" element={<HelpPage/>}/><Route path="/properties" element={<PropertiesPage/>}/><Route path="/tenants" element={<TenantsPage/>}/><Route path="/agreements" element={<AgreementsPage/>}/><Route path="/ledger" element={<LedgerPage/>}/><Route path="/deposits" element={<DepositsPage/>}/><Route path="/utilities" element={<UtilitiesPage/>}/><Route path="/inspections" element={<InspectionsPage/>}/><Route path="/reports" element={<ReportsPage/>}/><Route path="/maintenance" element={<MaintenancePage/>}/><Route path="*" element={<ComingSoon/>}/></Routes>
    </main>
  </div>
}

function ComingSoon() { return <div className="content"><div className="panel empty-state"><span>✳</span><h3>This workspace is still in development</h3><p>This section will appear here as its backend and data flows are implemented.</p></div></div> }
export default App
