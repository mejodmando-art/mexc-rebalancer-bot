import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MEXC Smart Portfolio',
  description: 'Auto-rebalancing portfolio bot for MEXC Spot',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body>
        {children}
      </body>
    </html>
  );
}
