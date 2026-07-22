import fs from "node:fs";

import {
  E2E_AUTH_META_PATH,
  ensureE2EEnvLoaded,
  hasE2EAuthEnv,
} from "./e2e-auth-state";

/**
 * e2e 已登录态 global teardown：用 service role 清空专用测试用户的
 * user_style_favorites（测试写入本就被 RLS 锁在该用户行内）。
 * 元信息文件缺失 / 环境变量不齐时静默跳过。
 */
async function globalTeardown(): Promise<void> {
  ensureE2EEnvLoaded();
  if (!hasE2EAuthEnv()) return;
  if (!fs.existsSync(E2E_AUTH_META_PATH)) return;

  let userId: string | null = null;
  try {
    const meta = JSON.parse(fs.readFileSync(E2E_AUTH_META_PATH, "utf8")) as {
      userId?: unknown;
    };
    userId = typeof meta.userId === "string" && meta.userId ? meta.userId : null;
  } catch {
    userId = null;
  }
  if (!userId) return;

  const supabaseUrl = process.env.SUPABASE_URL as string;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY as string;
  const res = await fetch(
    `${supabaseUrl}/rest/v1/user_style_favorites?user_id=eq.${userId}`,
    {
      method: "DELETE",
      headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
    },
  );
  if (!res.ok) {
    console.warn(`[e2e] 清理测试用户收藏失败：HTTP ${res.status}`);
  } else {
    console.log("[e2e] 已清空测试用户收藏");
  }
}

export default globalTeardown;
