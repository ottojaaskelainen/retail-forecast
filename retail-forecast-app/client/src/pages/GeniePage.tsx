import { GenieSpace } from '@databricks/appkit-ui/react';

export function GeniePage() {
  return (
    <div className="p-6">
      <GenieSpace spaceId={import.meta.env.VITE_GENIE_SPACE_ID ?? ""} />
    </div>
  );
}
