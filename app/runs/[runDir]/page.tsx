import { notFound } from "next/navigation";

import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

import { RunDetailClientPage } from "./run-detail-client";

type RunDetailPageProps = {
  params: Promise<{ runDir: string | string[] }>;
};

function readRunDir(value: string | string[] | undefined): string {
  if (!value) {
    return "";
  }

  return Array.isArray(value) ? value[0] ?? "" : value;
}

export default async function RunDetailPage({
  params,
}: RunDetailPageProps) {
  const resolvedParams = await params;
  const runDir = readRunDir(resolvedParams?.runDir);

  if (!isValidRunDir(runDir)) {
    notFound();
  }

  const supabase = await createSupabaseAuthClient();
  const { data, error } = await supabase
    .from("runs")
    .select("run_dir")
    .eq("run_dir", runDir)
    .maybeSingle();

  if (error) {
    throw new Error("Failed to load run detail page");
  }

  if (!data) {
    notFound();
  }

  return <RunDetailClientPage runDir={runDir} />;
}
