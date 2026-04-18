import { isValidRunDir } from "@/lib/comfyui-types";
import { privateObjectUrl, publicObjectUrl } from "@/lib/r2-url";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  ImageCategory,
  R2Bucket,
  SupabaseRunGridItemRow,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

type VariantUrls = {
  webp?: string;
  avif?: string;
};

function parseNonNegativeInt(raw: string | null): number | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!/^[0-9]+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  if (!Number.isSafeInteger(n) || n < 0) return null;
  return n;
}

function isMissingAuthSessionError(error: Error | null): boolean {
  if (!error) {
    return false;
  }

  return error.message.toLowerCase().includes("auth session missing");
}

function urlFromVariant(bucket: R2Bucket, r2Key: string): string {
  return bucket === "public" ? publicObjectUrl(r2Key) : privateObjectUrl(r2Key);
}

function nullableUrl(
  bucket: R2Bucket | null | undefined,
  r2Key: string | null | undefined,
): string | null {
  if (!bucket || !r2Key) return null;
  return urlFromVariant(bucket, r2Key);
}

function buildDisplayImage(image: SupabaseRunGridItemRow): VariantUrls | null {
  const displayWebp = nullableUrl(
    image.display_webp_bucket,
    image.display_webp_r2_key,
  );
  const displayAvif = nullableUrl(
    image.display_avif_bucket,
    image.display_avif_r2_key,
  );

  if (displayWebp || displayAvif) {
    return {
      webp: displayWebp ?? undefined,
      avif: displayAvif ?? undefined,
    };
  }

  return null;
}

function requiresAuthenticatedViewer(category: ImageCategory): boolean {
  return category !== "normal";
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const url = new URL(request.url);
    const xIndex = parseNonNegativeInt(url.searchParams.get("x_index"));
    const yIndex = parseNonNegativeInt(url.searchParams.get("y_index"));
    const batchIndex = parseNonNegativeInt(url.searchParams.get("batch_index"));
    if (xIndex === null || yIndex === null || batchIndex === null) {
      return Response.json({ error: "Invalid image coordinates" }, { status: 400 });
    }

    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("run_grid_items")
      .select(
        "run_dir,x_index,y_index,batch_index,category,width,height,blurhash,display_webp_bucket,display_webp_r2_key,display_avif_bucket,display_avif_r2_key",
      )
      .eq("run_dir", runDir)
      .eq("x_index", xIndex)
      .eq("y_index", yIndex)
      .eq("batch_index", batchIndex)
      .maybeSingle();

    if (error) {
      return Response.json({ error: "Failed to load run image" }, { status: 500 });
    }

    const image = data as SupabaseRunGridItemRow | null;
    if (!image) {
      return Response.json({ error: "Image not found" }, { status: 404 });
    }

    if (requiresAuthenticatedViewer(image.category)) {
      const {
        data: { user },
        error: userError,
      } = await supabase.auth.getUser();

      if (userError) {
        if (isMissingAuthSessionError(userError)) {
          return Response.json(
            { error: "Authentication required" },
            { status: 401 },
          );
        }

        return Response.json(
          { error: "Failed to load run image" },
          { status: 500 },
        );
      }

      if (!user) {
        return Response.json(
          { error: "Authentication required" },
          { status: 401 },
        );
      }
    }

    const displayImage = buildDisplayImage(image);
    if (!displayImage) {
      return Response.json({ error: "Image not found" }, { status: 404 });
    }

    return Response.json(
      {
        run_dir: runDir,
        x_index: xIndex,
        y_index: yIndex,
        batch_index: batchIndex,
        image: displayImage,
      },
      {
        headers: {
          "Cache-Control": "private, no-store, max-age=0",
          Vary: "Cookie",
        },
      },
    );
  } catch {
    return Response.json({ error: "Failed to load run image" }, { status: 500 });
  }
}
