import HomePageClient from "./home-page-client";

import { listRunSummaries } from "@/lib/run-list";

export default async function Page() {
  let runs: Awaited<ReturnType<typeof listRunSummaries>> = [];
  let hasError = false;

  try {
    runs = await listRunSummaries();
  } catch {
    hasError = true;
  }

  return <HomePageClient runs={runs} hasError={hasError} />;
}
