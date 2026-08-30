import type { Metadata } from "next";

/* The pilot page is a client component (it runs a form), so it cannot export
 * metadata itself. This server layout gives it a real title and description. */
export const metadata: Metadata = {
  title: "Book a design-partner pilot",
  description:
    "Request a hands-on OMEM design-partner pilot. Over a couple of weeks we put the approval gate and provenance trail into your agent, so you can show a client's compliance team why it did what it did. $1,500.",
};

export default function PilotLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
