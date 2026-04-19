import { isValidRunDir } from "@/lib/comfyui-types";
import {
  privateObjectUrlWithMetadata,
  privateSignedUrlResponseMaxAgeSeconds,
  privateSignedUrlTtlSeconds,
  publicObjectUrl,
} from "@/lib/r2-url";
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
  bucket: R2Bucket;
  cache_key: string;
  url: string;
};

type VariantSources = {
  webp?: VariantUrls;
  avif?: VariantUrls;
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

function nullableResolvedVariant(
  bucket: R2Bucket | null | undefined,
  r2Key: string | null | undefined,
  cacheKey: string | null | undefined,
  signedAt: Date,
): VariantUrls | null {
  if (!bucket && !r2Key && !cacheKey) return null;
  if (!bucket || !r2Key || !cacheKey) {
    throw new Error("Invalid display variant payload");
  }

  if (bucket === "public") {
    return {
      bucket,
      cache_key: cacheKey,
      url: publicObjectUrl(r2Key),
    };
  }

  const signed = privateObjectUrlWithMetadata(r2Key, signedAt);
  return {
    bucket,
    cache_key: cacheKey,
    url: signed.url,
  };
}

function buildDisplayImage(
  image: SupabaseRunGridItemRow,
  signedAt: Date,
): VariantSources | null {
  const displayWebp = nullableResolvedVariant(
    image.display_webp_bucket,
    image.display_webp_r2_key,
    image.display_webp_cache_key,
    signedAt,
  );
  const displayAvif = nullableResolvedVariant(
    image.display_avif_bucket,
    image.display_avif_r2_key,
    image.display_avif_cache_key,
    signedAt,
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
    const signingAt = new Date();
    const signedUrlTtlSeconds = privateSignedUrlTtlSeconds();
    const responseMaxAge = privateSignedUrlResponseMaxAgeSeconds();
    const { data, error } = await supabase
      .from("run_grid_items")
      .select(
        "run_dir,x_index,y_index,batch_index,category,width,height,blurhash,display_webp_bucket,display_webp_r2_key,display_webp_cache_key,display_avif_bucket,display_avif_r2_key,display_avif_cache_key",
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

    const displayImage = buildDisplayImage(image, signingAt);
    if (!displayImage) {
      return Response.json({ error: "Image not found" }, { status: 404 });
    }

    return Response.json(
      {
        run_dir: runDir,
        x_index: xIndex,
        y_index: yIndex,
        batch_index: batchIndex,
        signed_url_expires_at: new Date(
          signingAt.getTime() + signedUrlTtlSeconds * 1000,
        ).toISOString(),
        image: displayImage,
      },
      {
        headers: {
          "Cache-Control": `private, max-age=${responseMaxAge}`,
          Vary: "Cookie",
        },
      },
    );
  } catch {
    return Response.json({ error: "Failed to load run image" }, { status: 500 });
  }
}
