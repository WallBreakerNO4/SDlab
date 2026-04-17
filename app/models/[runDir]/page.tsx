import { notFound } from "next/navigation";

import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

import { ModelDetailClientPage } from "./model-detail-client";

type ModelDetailPageProps = {
  params: Promise<{ runDir: string | string[] }>;
};

function readRunDir(value: string | string[] | undefined): string {
  if (!value) {
    return "";
  }

  return Array.isArray(value) ? value[0] ?? "" : value;
}

export default async function ModelDetailPage({
  params,
}: ModelDetailPageProps) {
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
    throw new Error("Failed to load model detail page");
  }

  if (!data) {
    notFound();
  }

  return <ModelDetailClientPage runDir={runDir} />;
}
