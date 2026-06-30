import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { RiskDashboardPage } from './pages/RiskDashboardPage';
import { GeniePage } from './pages/GeniePage';

const NAV_LINKS = [
  { to: '/risk',  label: 'Risk Dashboard' },
  { to: '/genie', label: 'Ask the Data' },
];

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#f9fafb' }}>
      <header style={{ borderBottom: '1px solid #e5e7eb', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '16px', background: '#fff' }}>
        <span style={{ fontWeight: '600', fontSize: '1rem' }}>Retail Forecast</span>
        <nav style={{ display: 'flex', gap: '4px' }}>
          {NAV_LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => ({
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: '500',
                textDecoration: 'none',
                background: isActive ? '#1e40af' : 'transparent',
                color: isActive ? '#fff' : '#6b7280',
              })}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main style={{ flex: 1, padding: '24px' }}>{children}</main>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/risk" replace />} />
          <Route path="/risk"  element={<RiskDashboardPage />} />
          <Route path="/genie" element={<GeniePage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
