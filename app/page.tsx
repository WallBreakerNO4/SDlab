import HomePageClient from "./home-page-client";

import { listRunSummaries } from "@/lib/run-list";

export default async function Page() {
  let models: Awaited<ReturnType<typeof listRunSummaries>> = [];
  let hasError = false;

  try {
    models = await listRunSummaries();
  } catch {
    hasError = true;
  }

  return <HomePageClient models={models} hasError={hasError} />;
}
