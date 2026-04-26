import type { Metadata } from "next";
import { Orbitron, Rajdhani } from "next/font/google";

import "./globals.css";

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
});

const rajdhani = Rajdhani({
  subsets: ["latin"],
  variable: "--font-rajdhani",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Aura-G4 Tactical Operations Center",
  description: "Obsidian tactical command interface for Aura-G4.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${orbitron.variable} ${rajdhani.variable} antialiased`}>{children}</body>
    </html>
  );
}
