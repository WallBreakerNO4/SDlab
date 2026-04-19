import HomePageClient from "./home-page-client";

import { listRunSummaries } from "@/lib/run-list";

export default async function Page() {
  const models = await listRunSummaries();
  return <HomePageClient models={models} />;
}
