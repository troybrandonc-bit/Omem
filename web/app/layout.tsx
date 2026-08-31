import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import { fontVars } from "./fonts";

const SITE_TITLE = "OMEM / accountability for the AI agents you ship";
const SITE_DESC =
  "OMEM keeps AI agents answerable: an audit trail of what the agent believed and when, and a human approval gate before a risky action runs. Built on a belief-revision engine that keeps contradictions and proves provenance. Self-hosted, MIT, no dependencies.";

export const metadata: Metadata = {
  // Resolves relative OG/canonical URLs and the icon below. Set to the product
  // site; the commons runs on its own domain with its own metadata.
  metadataBase: new URL("https://infrastructure.omem-cloud.com"),
  title: {
    default: SITE_TITLE,
    template: "%s / OMEM",
  },
  description: SITE_DESC,
  applicationName: "OMEM",
  formatDetection: { telephone: false },
  // Self-referencing canonical on every page, resolved per-route against
  // metadataBase. Matters doubly here: the dev.to syndication canonicals to
  // this domain, and the site should claim its own URLs in return.
  alternates: { canonical: "./" },
  openGraph: {
    type: "website",
    siteName: "OMEM",
    title: SITE_TITLE,
    description: SITE_DESC,
    url: "/",
    images: ["/icon.png"],
  },
  twitter: {
    card: "summary",
    title: SITE_TITLE,
    description: SITE_DESC,
    images: ["/icon.png"],
  },
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
/* Cloudflare Web Analytics: cookieless, aggregate, no profile, which is what
 * the privacy page promises. Renders nothing until a token is set. To turn it
 * on: Cloudflare dashboard -> Web Analytics -> Add a site
 * (infrastructure.omem-cloud.com) -> paste the token string here. */
const CF_ANALYTICS_TOKEN = "92eda3437ae944c99c0f668453ae69f3";

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
        {CF_ANALYTICS_TOKEN && (
          <script defer src="https://static.cloudflareinsights.com/beacon.min.js"
            data-cf-beacon={`{"token": "${CF_ANALYTICS_TOKEN}"}`} />
        )}
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
