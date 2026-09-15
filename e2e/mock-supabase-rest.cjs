/**
 * no-env e2e 的假 Supabase REST 端点。
 *
 * 首页与详情页的 generateMetadata 在服务端查询 `run_list_items`；无密钥模式下
 * 没有真实 Supabase，这里用固定数据补齐服务端渲染所需的查询，涵盖一张进行中
 * 卡片与一张已完结卡片（published_at 顺序与 created_at 相反）。
 */
/* eslint-disable @typescript-eslint/no-require-imports -- no-env e2e 的 CommonJS 运行时脚本 */
const http = require("node:http");

const RUN_LIST_ITEMS = require("./no-env-home-run-list.json");

function filterRows(rows, searchParams) {
  return rows.filter((row) => {
    for (const [key, value] of searchParams) {
      if (key === "select" || key === "order" || key === "limit" || key === "offset") {
        continue;
      }
      if (!value.startsWith("eq.")) {
        continue;
      }
      if (String(row[key]) !== value.slice(3)) {
        return false;
      }
    }
    return true;
  });
}

function applyOrder(rows, order) {
  if (!order) {
    return rows;
  }
  const [field, direction] = order.split(".");
  const factor = direction === "desc" ? -1 : 1;
  return [...rows].sort((left, right) => {
    const a = left[field];
    const b = right[field];
    if (a === b) return 0;
    return (a < b ? -1 : 1) * factor;
  });
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

function createMockSupabaseRestServer() {
  return http.createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");

    if (url.pathname === "/__health") {
      sendJson(response, 200, { ok: true });
      return;
    }

    if (!url.pathname.startsWith("/rest/v1/")) {
      sendJson(response, 404, { message: "not found" });
      return;
    }

    const table = url.pathname.slice("/rest/v1/".length);
    const sourceRows = table === "run_list_items" ? RUN_LIST_ITEMS : [];
    let rows = filterRows(sourceRows, url.searchParams);
    rows = applyOrder(rows, url.searchParams.get("order"));

    const limit = Number(url.searchParams.get("limit"));
    if (Number.isFinite(limit) && limit > 0) {
      rows = rows.slice(0, limit);
    }

    const accept = String(request.headers.accept ?? "");
    if (accept.includes("vnd.pgrst.object+json")) {
      sendJson(response, 200, rows.length === 1 ? rows[0] : null);
      return;
    }

    response.writeHead(200, {
      "content-type": "application/json",
      "content-range": `0-${Math.max(0, rows.length - 1)}/${rows.length}`,
    });
    response.end(JSON.stringify(rows));
  });
}

function startMockSupabaseRestServer({ port }) {
  const server = createMockSupabaseRestServer();
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve(server);
    });
  });
}

module.exports = {
  RUN_LIST_ITEMS,
  createMockSupabaseRestServer,
  startMockSupabaseRestServer,
};
