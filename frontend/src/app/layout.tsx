import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MAS Usability Tester',
  description: 'Automated UI accessibility evaluation and repair system',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
