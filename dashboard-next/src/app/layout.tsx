import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "CopilotLens — Elegant code intelligence for GitHub Copilot",
  description:
    "A sleek Apple-inspired dashboard for codebase health, dependency graphs, git hotspots, dead code, and blast radius context.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <head>
        <Script
          src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"
          strategy="beforeInteractive"
        />
      </head>
      <body className="min-h-full flex flex-col bg-[var(--background)] text-[var(--text-primary)] font-sans selection:bg-[#0071e3]/20 selection:text-[#0f172a]">
        {children}
      </body>
    </html>
  );
}
