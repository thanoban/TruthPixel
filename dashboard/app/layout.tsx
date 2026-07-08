import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TruthPixel Reviewer Dashboard",
  description:
    "Reviewer queue and claim decision surface for TruthPixel image-integrity checks.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
