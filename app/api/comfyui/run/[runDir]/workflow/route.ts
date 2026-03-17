import { getCloudflareContext } from "@opennextjs/cloudflare";

import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isValidWorkflowArtifactKey(runDir: string, r2Key: string): boolean {
  return (
    r2Key.startsWith(`runs/${runDir}/artifacts/workflow/`) &&
    r2Key.endsWith(".json")
  );
}

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return jsonError(404, "Run not found");
    }

    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("runs")
      .select("workflow_download_r2_key")
      .eq("run_dir", runDir)
      .maybeSingle();

    if (error) {
      return jsonError(500, "Failed to download workflow");
    }

    const workflowKey = data?.workflow_download_r2_key;
    if (
      typeof workflowKey !== "string" ||
      !isValidWorkflowArtifactKey(runDir, workflowKey)
    ) {
      return jsonError(404, "Workflow not found");
    }

    const { env } = getCloudflareContext();
    const object = await env.R2_PUBLIC_BUCKET.get(workflowKey);
    if (object === null) {
      return jsonError(404, "Workflow not found");
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.set(
      "Content-Disposition",
      `attachment; filename="${runDir}-workflow.json"`,
    );
    headers.set("Cache-Control", "public, max-age=31536000, immutable");
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);

    return new Response(object.body, { status: 200, headers });
  } catch {
    return jsonError(500, "Failed to download workflow");
  }
}
