import type { Metadata } from "next";

/* The readiness check is a client component (it scores answers in the
 * browser), so it cannot export metadata itself. This server layout gives it a
 * real title and description. */
export const metadata: Metadata = {
  title: "Is your AI agent's record good enough to survive an audit?",
  description:
    "Eleven questions about what your agent actually records, scored against the four Testimony Record conformance levels. Nothing is uploaded, nothing is stored, no signup. You get the level you reach today and the specific gaps between you and the next one.",
};

export default function CheckLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
