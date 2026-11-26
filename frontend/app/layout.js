import './globals.css';
import Nav from '@/components/Nav';
import Providers from './providers';

export const metadata = {
  title: 'DocIntel',
  description: 'Upload, review and search invoices',
};

// The root layout is a server component: it only renders the frame. The pages inside are
// client components because they are interactive and poll for live data.
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <Nav />
          <main>{children}</main>
        </Providers>
      </body>
    </html>
  );
}