import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TruthPixel — image integrity check",
  description: "Multi-signal image-integrity verification: AI-generation, edit forensics, and screenshot/recapture detection in one fused report.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
