import { isValidRunDir } from "@/lib/comfyui-types";
import { notFound } from "next/navigation";

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

  return <ModelDetailClientPage runDir={runDir} />;
}
