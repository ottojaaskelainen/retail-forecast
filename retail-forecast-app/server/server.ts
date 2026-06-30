import { createApp, analytics, genie, server } from '@databricks/appkit';

const app = createApp({
  plugins: [
    analytics(),
    // TODO Task 10: wire in genie space id
    genie({ spaceId: process.env.VITE_GENIE_SPACE_ID ?? '' }),
    server(),
  ],
});

app.start();
