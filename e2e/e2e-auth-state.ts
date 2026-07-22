import path from "node:path";

/**
 * e2e 已登录态共享约定（spec 决策记录 13，spike: .cache/cp3-spike/spike.mjs）。
 *
 * - 全库仅一个专用测试用户，远端 create-or-ignore 幂等；
 * - global setup 建 session 并写 storageState，已登录用例经 test.use 复用；
 * - global teardown 用 service role 清空该测试用户的 user_style_favorites；
 * - 缺 Supabase 环境变量时不写 state，已登录用例自行 skip（仿 task-10 skip 模式）。
 */

/** e2e 专用测试用户邮箱（固定，仓库不留测试凭证） */
export const E2E_TEST_USER_EMAIL = "e2e-style-favorites@sds.lab";

/** 已登录用例复用的 storageState 路径（global setup 写入；test-results 已 gitignore） */
export const E2E_AUTH_STATE_PATH = path.resolve(
  __dirname,
  "../test-results/e2e-auth-state.json",
);

/** global teardown 清理收藏所需的测试用户元信息路径（setup 写入 userId） */
export const E2E_AUTH_META_PATH = path.resolve(
  __dirname,
  "../test-results/e2e-auth-state.meta.json",
);

let envLoadAttempted = false;

/**
 * e2e 进程默认不读 .env；幂等加载（Node 24 `process.loadEnvFile`，不覆盖已有变量）。
 * 无文件 / 不可读时静默，按「未配置」处理。
 */
export function ensureE2EEnvLoaded(): void {
  if (envLoadAttempted) return;
  envLoadAttempted = true;
  try {
    process.loadEnvFile(".env");
  } catch {
    // 无 .env：已登录用例将按缺环境变量跳过
  }
}

/** 已登录用例所需环境变量是否齐备（缺一则跳过） */
export function hasE2EAuthEnv(): boolean {
  ensureE2EEnvLoaded();
  return Boolean(
    process.env.SUPABASE_URL &&
      process.env.SUPABASE_SERVICE_ROLE_KEY &&
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  );
}
