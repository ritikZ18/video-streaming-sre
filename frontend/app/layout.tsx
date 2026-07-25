import type { ReactNode } from "react";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "../index.css";

// Inter, self-hosted by next/font. Falls back to the system stack (SF on macOS)
// via the tailwind fontFamily config until it's ready.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "StreamSRE",
  description: "Mini HLS video streaming platform with SRE focus",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      {/* Base color + ambient top wash live in index.css so class ordering can't
          flatten them back to black. */}
      <body className="min-h-screen font-sans text-white antialiased">
        {children}
      </body>
    </html>
  );
}
