"use client";

import { useReportWebVitals } from "next/web-vitals";

function sendMetric(name: string, value: number, extra: Record<string, unknown>) {
  const payload = {
    name,
    value,
    route: typeof window !== "undefined" ? window.location.pathname : "",
    navigationType:
      "navigation" in window && window.navigation
        ? (window.navigation as { type?: string }).type
        : undefined,
    ...extra,
  };

  navigator.sendBeacon(
    "/api/telemetry/web-vitals",
    new Blob([JSON.stringify(payload)], { type: "application/json" }),
  );
}

export function WebVitals() {
  useReportWebVitals((metric) => {
    const extra: Record<string, unknown> = {};

    if ("id" in metric) {
      extra.metricId = metric.id;
    }
    if ("rating" in metric) {
      extra.rating = metric.rating;
    }
    if ("navigationType" in metric) {
      extra.navigationType = metric.navigationType;
    }

    sendMetric(metric.name, Math.round(metric.value), extra);
  });

  return null;
}
