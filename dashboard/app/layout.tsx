import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { AuthHeader } from "./auth-header";
import { ThemeToggle } from "./theme-toggle";
import { noFlashThemeScript } from "./theme";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TruthPixel Reviewer Dashboard",
  description:
    "Reviewer queue and claim decision surface for TruthPixel image-integrity checks.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${ibmPlexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Sets data-theme before first paint so there's no flash of the wrong theme —
            must run before hydration, hence a plain inline script rather than a component. */}
        <script dangerouslySetInnerHTML={{ __html: noFlashThemeScript }} />
      </head>
      <body>
        <div className="grid-overlay" />
        <nav className="top-nav">
          <div className="brand">
            <span className="brand-dot" />
            <span>TruthPixel</span>
            <span className="brand-tag">// case-review console</span>
          </div>
          <div className="header-actions">
            <AuthHeader />
            <ThemeToggle />
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
