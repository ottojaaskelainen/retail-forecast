import { AppLayout, NavItem } from '@databricks/appkit-ui/react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { RiskDashboardPage } from './pages/RiskDashboardPage';
import { GeniePage } from './pages/GeniePage';

export function App() {
  return (
    <BrowserRouter>
      <AppLayout
        nav={[
          <NavItem key="risk" to="/risk" label="Risk Dashboard" />,
          <NavItem key="genie" to="/genie" label="Ask the Data" />,
        ]}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/risk" replace />} />
          <Route path="/risk"  element={<RiskDashboardPage />} />
          <Route path="/genie" element={<GeniePage />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}
