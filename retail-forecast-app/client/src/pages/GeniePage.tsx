import { GenieChat } from '@databricks/appkit-ui/react';

export function GeniePage() {
  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '8px' }}>Ask the Data</h2>
      <p style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '16px' }}>
        Ask natural language questions about demand forecasts, promotions, and inventory risks.
      </p>
      <div style={{ height: 'min(600px, 70vh)', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden' }}>
        <GenieChat alias="default" />
      </div>
    </div>
  );
}
