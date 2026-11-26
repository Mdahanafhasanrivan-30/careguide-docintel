'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  ['/', 'Upload'],
  ['/documents', 'Documents'],
  ['/search', 'Search'],
];

export default function Nav() {
  const path = usePathname();
  const active = (href) => (href === '/' ? path === '/' : path.startsWith(href));
  return (
    <header className="nav">
      <strong>DocIntel</strong>
      <nav>
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={active(href) ? 'active' : ''}>{label}</Link>
        ))}
      </nav>
    </header>
  );
}