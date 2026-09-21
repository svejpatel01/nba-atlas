"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./site-nav.module.css";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/style-map", label: "Style map" },
  { href: "/ask", label: "Ask" },
  { href: "/shot-quality", label: "Shot quality" },
  { href: "/game-flow", label: "Game flow" },
  { href: "/methodology", label: "Methodology" },
];

export default function SiteNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.nav}>
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={pathname === link.href ? styles.activeLink : styles.link}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
