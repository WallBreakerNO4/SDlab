import { listRunSummaries } from "@/lib/run-list";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const runs = await listRunSummaries();
    return Response.json(runs);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to load runs";
    console.error("[api/comfyui/runs]", error);
    return Response.json({ error: message }, { status: 500 });
  }
}
