import type { ReactNode } from "react";
import type { Metadata } from "next";
import "../index.css";

export const metadata: Metadata = {
  title: "StreamSRE",
  description: "Mini HLS video streaming platform with SRE focus",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className="dark">
      {/* Base color + ambient top wash live in index.css so class ordering can't
          flatten them back to black. */}
      <body className="min-h-screen font-sans text-white antialiased">
        {children}
      </body>
    </html>
  );
}
