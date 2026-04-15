import { listRunSummaries } from "@/lib/run-list";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const runs = await listRunSummaries();
    return Response.json(runs);
  } catch {
    return Response.json({ error: "Failed to load runs" }, { status: 500 });
  }
}
