import { getCloudflareContext } from "@opennextjs/cloudflare";

import { isValidRunDir } from "@/lib/comfyui-types";
import { writeR2HttpMetadata } from "@/lib/r2-response";
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

function isMissingAuthSessionError(error: Error | null): boolean {
  if (!error) {
    return false;
  }

  return error.message.toLowerCase().includes("auth session missing");
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
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError) {
      if (isMissingAuthSessionError(userError)) {
        return jsonError(401, "Authentication required");
      }

      return jsonError(500, "Failed to download workflow");
    }

    if (!user) {
      return jsonError(401, "Authentication required");
    }

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
    writeR2HttpMetadata(headers, object);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.set(
      "Content-Disposition",
      `attachment; filename="${runDir}-workflow.json"`,
    );
    headers.set("Cache-Control", "private, no-store, max-age=0");
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    headers.set("Vary", "Cookie");

    return new Response(object.body, { status: 200, headers });
  } catch {
    return jsonError(500, "Failed to download workflow");
  }
}
