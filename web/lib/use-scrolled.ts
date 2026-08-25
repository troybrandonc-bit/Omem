"use client";
import { useEffect, useState } from "react";

/**
 * Has the page scrolled far enough that a sticky bar is actually covering
 * something?
 *
 * This exists for the scroll edge (`.chrome-bar` / `.is-lifted` in globals.css).
 * Every sticky header on the site drew a hairline and a blur permanently, which
 * meant that at the top of a page — the state a reader is in when they arrive —
 * the site opened with a rule ruled across nothing and a blur over paper. A
 * separator is only doing work once there is content passing beneath it.
 *
 * Cheap on purpose: a passive listener reading `scrollY` against one threshold,
 * with the state written only when the boolean flips, so it re-renders twice per
 * page rather than once per frame. `{ passive: true }` keeps it off the scroll
 * critical path.
 *
 * The initial read happens in the effect rather than in the initial state, so
 * the server-rendered markup and the first client render agree; a page restored
 * mid-scroll then corrects on the first commit.
 */
export function useScrolled(threshold = 8) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    let last = false;
    const read = () => {
      const next = window.scrollY > threshold;
      if (next !== last) { last = next; setScrolled(next); }
    };
    read();
    window.addEventListener("scroll", read, { passive: true });
    return () => window.removeEventListener("scroll", read);
  }, [threshold]);

  return scrolled;
}
