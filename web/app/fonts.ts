/* No webfonts.
 *
 * The dashboard used to pull Inter, Inter Tight and Spline Sans Mono through
 * next/font. It now sets type to the platform's own system family instead --
 * San Francisco on Apple hardware, Segoe UI / Cascadia on Windows -- defined as
 * --font-sans / --font-display / --font-mono in app/globals.css. That is the
 * Apple way to do type on the web (use the OS font, do not approximate it), and
 * it means the dashboard downloads no font files at all, which is what "runs on
 * your own machine, with no external services" always implied.
 *
 * Kept as an empty export so nothing that once imported it breaks. */
export const fontVars = "";
