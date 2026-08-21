import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "OMEM / trustworthy memory for AI agents",
  description: "Give your AI memory it can prove.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers><Shell>{children}</Shell></Providers>
      </body>
    </html>
  );
}
