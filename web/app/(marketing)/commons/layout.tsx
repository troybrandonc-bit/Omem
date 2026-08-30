import type { Metadata } from "next";

/* The commons page is a client component (it reads /v1/commons/public at
 * runtime), so it cannot export metadata itself. This server layout gives it a
 * real title and description instead of inheriting the product's "memory for AI
 * agents" default, and canonicalises to the collector domain — the commons is
 * the whole site at commons.omem-cloud.com and only a describe-page here, so
 * both URLs should consolidate to the live one. */
export const metadata: Metadata = {
  title: "The OMEM commons",
  description:
    "An anonymous, opt-in record of how people behave, contributed by OMEM installations and offered CC BY 4.0 for training AI on human nature — without holding a single fact about a person.",
  alternates: { canonical: "https://commons.omem-cloud.com/commons" },
  openGraph: {
    title: "The OMEM commons",
    description:
      "An anonymous, opt-in behavioural dataset for training AI, held by no one. CC BY 4.0.",
    url: "https://commons.omem-cloud.com/commons",
    images: ["/icon.png"],
  },
};

export default function CommonsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
