import { Inter, Inter_Tight, Spline_Sans_Mono } from "next/font/google";

/* Fonts are self-hosted at build time, not fetched from Google at runtime.
 *
 * next/font downloads the files at build time, emits them as same-origin
 * assets, and generates a metrics-matched local fallback so the swap does not
 * shift layout. Nothing is requested from a third party at runtime — which
 * matters because the landing page claims OMEM "runs on your own machine, with
 * no external services", and the dashboard ships inside a Python wheel.
 *
 * THREE FAMILIES, AND ALL THREE ARE VARIABLE.
 *
 * This was IBM Plex Sans + Plex Mono + Plex Serif. Plex is a good family, but
 * using one superfamily for every job is the single loudest tell that nobody
 * chose the type: there is no contrast between display and text because they
 * are the same face at different sizes, and Plex's slightly institutional
 * warmth is the opposite of sleek.
 *
 * Variable matters here beyond file size. A static family gives you 400/500/600
 * and nothing between, so "slightly heavier" is not available and every weight
 * decision snaps to a step somebody else chose. The display face can sit at 560
 * where 600 is heavy and 500 is limp, and the whole range is one file.
 */

/** Body, UI, everything that is read rather than announced.
 *  Inter is drawn for screens at text sizes: tall x-height, open apertures,
 *  unambiguous 1/l/I. It is deliberately characterless — the display face
 *  carries the personality, and text type that has opinions gets tiring. */
export const sans = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
  fallback: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
});

/** Display. Inter Tight is Inter with the sidebearings pulled in and the
 *  proportions narrowed — built for exactly the job of being set large.
 *
 *  Using Inter for a 64px headline is what makes a headline look like body copy
 *  that was enlarged: at display sizes the spacing that keeps 15px text legible
 *  reads as gaps. Tight closes them. It is the same skeleton as the body face,
 *  so the page still reads as one voice rather than two fonts stapled together;
 *  it is just the version of that voice drawn for size. */
export const display = Inter_Tight({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
  fallback: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
});

/** Identifiers, propositions, code.
 *  Was JetBrains Mono, whose slashed zero and slab-ish terminals read as a
 *  coder's typewriter next to Inter's clean humanist text. Spline Sans Mono is
 *  a humanist monospace built as a companion to a modern sans: it keeps the
 *  fixed advance a token needs for `not:prefers_email_over_phone`, but the
 *  letterforms are Inter's world, not a terminal's, so an id set in it reads as
 *  part of the same sleek document rather than a machine printout. Variable,
 *  like the other two faces. */
export const mono = Spline_Sans_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
});

export const fontVars = `${sans.variable} ${display.variable} ${mono.variable}`;
