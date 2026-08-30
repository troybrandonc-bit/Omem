import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

/* Geist, self-hosted, both faces.
 *
 * WHY GEIST AND NOT A SYSTEM STACK OR INTER.
 *
 * The system stack gave real San Francisco on Apple hardware, but on Windows it
 * fell to Segoe UI, which reads as a generic OS default -- the "this was not
 * designed" look. Inter, before it, is the single most common webfont on the
 * internet, which is its own kind of anonymous. Geist is Vercel's product
 * typeface: a tight, confident neo-grotesque in the San Francisco lineage, with
 * a matching monospace drawn alongside it. It is what Linear- and Vercel-tier
 * product UIs are set in, and it looks the same on every machine, so the
 * dashboard reads as a designed product rather than a browser default -- while
 * still being self-hosted at build time (next/font), so nothing is fetched from
 * a third party at runtime and the wheel ships the files.
 *
 * GeistSans carries text AND display: the display treatment is size, weight and
 * negative tracking (see .display in globals.css), not a second family. GeistMono
 * carries every identifier and proposition. */
export const fontVars = `${GeistSans.variable} ${GeistMono.variable}`;
