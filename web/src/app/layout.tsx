import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MEXC Smart Portfolio',
  description: 'Smart portfolio auto-rebalancing – Bitget-style on MEXC',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" className="dark">
      <body>{children}</body>
    </html>
  );
}
