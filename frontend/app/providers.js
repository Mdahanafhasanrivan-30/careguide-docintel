'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

// Retry only when it can help: network errors (0) and server errors (5xx), at most twice.
// A 404 or 422 will not change by asking again.
const retry = (failures, error) => (error?.status === 0 || error?.status >= 500) && failures < 2;

export default function Providers({ children }) {
  // useState so the client is created once per browser tab, not on every render.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry, staleTime: 1000 } } }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}