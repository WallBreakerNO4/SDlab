import { Skeleton } from "@/components/ui/skeleton";

export function SummarySkeleton() {
  const keys = ["k1", "k2", "k3", "k4"];
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {keys.map((key) => (
        <div key={key} className="border p-3">
          <Skeleton className="mb-2 h-3 w-16" />
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  );
}

export function GridSkeleton() {
  const rowKeys = ["r1", "r2", "r3", "r4", "r5"];
  const cellKeys = ["c1", "c2", "c3", "c4", "c5", "c6"];
  return (
    <div className="space-y-2">
      {rowKeys.map((rowKey) => (
        <div key={rowKey} className="grid min-w-240 grid-cols-6 gap-2">
          {cellKeys.map((cellKey) => (
            <Skeleton key={`${rowKey}-${cellKey}`} className="h-32 w-full" />
          ))}
        </div>
      ))}
    </div>
  );
}
