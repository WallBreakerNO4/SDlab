export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  try {
    const body = await request.text();
    if (!body) {
      return new Response(null, { status: 204 });
    }

    const parsed: unknown = JSON.parse(body);
    if (typeof parsed !== "object" || parsed === null) {
      return new Response(null, { status: 204 });
    }

    const record = parsed as Record<string, unknown>;
    console.log(
      "[telemetry/web-vitals]",
      JSON.stringify({
        name: record.name,
        value: record.value,
        route: record.route,
        rating: record.rating,
        navigationType: record.navigationType,
      }),
    );
  } catch {
    // silently ignore parse errors
  }

  return new Response(null, { status: 204 });
}
