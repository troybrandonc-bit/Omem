import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import { fontVars } from "./fonts";

export const metadata: Metadata = {
  title: {
    default: "OMEM / memory for AI agents that refuses to decide what is true",
    template: "%s / OMEM",
  },
  description:
    "OMEM tracks what each agent believes, when it learned it, and why. It forms hunches from single examples, doubts them, and takes back conclusions when the facts under them die. Self-hosted, MIT, no dependencies.",
  applicationName: "OMEM",
  formatDetection: { telephone: false },
};

/* The dashboard is a dense instrument and the marketing site is a document, and
 * both have to survive a phone. `viewport-fit=cover` plus the safe-area padding
 * in the shells is what keeps content clear of a notch and a home indicator.
 * maximumScale is deliberately unset: capping zoom is the single most common
 * accessibility regression on a site like this one.
 *
 * themeColor is declared per scheme so the browser chrome matches the page
 * rather than flashing white above a charcoal app. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f6" },
    { media: "(prefers-color-scheme: dark)", color: "#171614" },
  ],
};

/* Theme, resolved before first paint.
 *
 * The theme used to be applied in a useEffect, which runs after hydration: a
 * dark-mode user got a full white page on every single navigation, then a
 * flash to charcoal. This runs synchronously in <head>, before the browser has
 * painted anything, so the first frame is already correct.
 *
 * It also now falls back to the OS preference instead of hard-coding "light",
 * which is what "respect the system appearance" means when nobody has chosen
 * yet. `suppressHydrationWarning` on <html> is required because this
 * deliberately mutates the class list before React sees it. */
const THEME_SCRIPT = `(function(){try{
var s=localStorage.getItem("omem-theme");
var d=s?s==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;
if(d)document.documentElement.classList.add("dark");
document.documentElement.style.colorScheme=d?"dark":"light";
}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fontVars} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {/* First stop in the tab order on every page. Reaching the content past
            a twenty-link sidebar was twenty tab stops before this existed. */}
        <a href="#main" className="skip-link">Skip to content</a>
        <Providers><Shell>{children}</Shell></Providers>
      </body>
    </html>
  );
}
