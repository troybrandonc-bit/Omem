import { redirect } from "next/navigation";

// No public landing page yet: send visitors straight to the dashboard.
export default function Home() {
  redirect("/overview");
}
