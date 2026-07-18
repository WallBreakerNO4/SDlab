import fs from "node:fs";
import path from "node:path";

import type { FullConfig } from "@playwright/test";

import {
  E2E_AUTH_META_PATH,
  E2E_AUTH_STATE_PATH,
  E2E_TEST_USER_EMAIL,
  ensureE2EEnvLoaded,
  hasE2EAuthEnv,
} from "./e2e-auth-state";

/** @supabase/ssr 0.8 浏览器端 cookie 分块阈值（spike 实测值，超过按 .0/.1 分块） */
const AUTH_COOKIE_CHUNK_SIZE = 3180;

/**
 * e2e 已登录态 global setup（spec 决策记录 13；参考实现 .cache/cp3-spike/spike.mjs）：
 *
 * 1. service role `POST /auth/v1/admin/users` 确保专用测试用户存在（已存在 422，幂等忽略）；
 * 2. `POST /auth/v1/admin/generate_link`（type magiclink）拿 action_link；
 * 3. `fetch(actionLink, { redirect: "manual" })` 从 Location 的
 *    `#access_token=...&refresh_token=...` fragment 截 tokens
 *    （远端 magiclink 走 implicit 流；redirect_to 白名单不含本地地址，手工截取一并绕开）；
 * 4. `GET /auth/v1/user`（apikey = publishable key + Bearer access_token）取 user 对象；
 * 5. 按 @supabase/ssr 0.8 编码构造 cookie（`sb-<ref>-auth-token`，
 *    `base64-` + base64url(JSON session)，超 3180 字符分块）写 storageState；
 * 6. 顺带预清测试用户收藏，保证本次运行从空收藏态开始。
 *
 * 全程 Node 侧 fetch 直连远端 Supabase，不需要浏览器 / 应用 server。
 * 缺 Supabase 环境变量时不写 state，已登录用例自行 skip。
 */
async function globalSetup(config: FullConfig): Promise<void> {
  ensureE2EEnvLoaded();
  if (!hasE2EAuthEnv()) {
    console.warn(
      "[e2e] 缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY，" +
        "跳过已登录用例（未登录用例仍运行）",
    );
    return;
  }

  const supabaseUrl = process.env.SUPABASE_URL as string;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY as string;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY as string;
  const projectRef = new URL(supabaseUrl).hostname.split(".")[0];

  // cookie domain 取被测 server 的 host（start 模式 127.0.0.1；dev 调试可指 localhost）
  const baseURL =
    (config.projects[0]?.use?.baseURL as string | undefined) ??
    `http://127.0.0.1:${process.env.E2E_PORT ?? "3000"}`;
  const cookieDomain = new URL(baseURL).hostname;

  const adminHeaders = {
    apikey: serviceKey,
    Authorization: `Bearer ${serviceKey}`,
    "Content-Type": "application/json",
  };

  // 1. 确保测试用户存在（密码随机、不落地；已存在 422，幂等忽略）
  const createRes = await fetch(`${supabaseUrl}/auth/v1/admin/users`, {
    method: "POST",
    headers: adminHeaders,
    body: JSON.stringify({
      email: E2E_TEST_USER_EMAIL,
      password: `${crypto.randomUUID()}Aa1!`,
      email_confirm: true,
    }),
  });
  if (createRes.status !== 200 && createRes.status !== 201 && createRes.status !== 422) {
    throw new Error(`[e2e] 创建测试用户失败：HTTP ${createRes.status}`);
  }

  // 2. generate_link 拿 action_link
  const linkRes = await fetch(`${supabaseUrl}/auth/v1/admin/generate_link`, {
    method: "POST",
    headers: adminHeaders,
    body: JSON.stringify({
      type: "magiclink",
      email: E2E_TEST_USER_EMAIL,
      options: { redirect_to: `${baseURL}/auth/callback` },
    }),
  });
  if (!linkRes.ok) {
    throw new Error(`[e2e] generate_link 失败：HTTP ${linkRes.status}`);
  }
  const linkBody = (await linkRes.json()) as {
    action_link?: string;
    properties?: { action_link?: string };
  };
  const actionLink = linkBody.action_link ?? linkBody.properties?.action_link;
  if (!actionLink) {
    throw new Error("[e2e] generate_link 响应缺少 action_link");
  }

  // 3. 手工 follow verify（不跟随跳转），从 Location fragment 截取 tokens
  const verifyRes = await fetch(actionLink, { redirect: "manual" });
  const location = verifyRes.headers.get("location") ?? "";
  let fragment = "";
  try {
    fragment = new URL(location).hash.slice(1);
  } catch {
    throw new Error(`[e2e] verify 响应 Location 不可解析：HTTP ${verifyRes.status}`);
  }
  const params = new URLSearchParams(fragment);
  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");
  if (!accessToken || !refreshToken) {
    throw new Error(`[e2e] verify fragment 无 tokens：HTTP ${verifyRes.status}`);
  }

  // 4. 取 user 对象
  const userRes = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: { apikey: publishableKey, Authorization: `Bearer ${accessToken}` },
  });
  if (!userRes.ok) {
    throw new Error(`[e2e] 获取测试用户信息失败：HTTP ${userRes.status}`);
  }
  const user = (await userRes.json()) as { id?: string };
  if (typeof user.id !== "string" || !user.id) {
    throw new Error("[e2e] /auth/v1/user 响应缺少 user.id");
  }

  // 5. 构造 @supabase/ssr 0.8 session cookie 并写 storageState
  const session = {
    access_token: accessToken,
    token_type: params.get("token_type") ?? "bearer",
    expires_in: Number(params.get("expires_in") ?? 3600),
    expires_at: Number(
      params.get("expires_at") ?? Math.floor(Date.now() / 1000) + 3600,
    ),
    refresh_token: refreshToken,
    user,
  };
  const encoded = `base64-${Buffer.from(JSON.stringify(session), "utf8").toString("base64url")}`;
  const cookieName = `sb-${projectRef}-auth-token`;
  const cookieChunks: Array<{ name: string; value: string }> = [];
  if (encoded.length <= AUTH_COOKIE_CHUNK_SIZE) {
    cookieChunks.push({ name: cookieName, value: encoded });
  } else {
    for (let i = 0, pos = 0; pos < encoded.length; i += 1, pos += AUTH_COOKIE_CHUNK_SIZE) {
      cookieChunks.push({
        name: `${cookieName}.${i}`,
        value: encoded.slice(pos, pos + AUTH_COOKIE_CHUNK_SIZE),
      });
    }
  }

  const storageState = {
    cookies: cookieChunks.map((chunk) => ({
      name: chunk.name,
      value: chunk.value,
      domain: cookieDomain,
      path: "/",
      expires: -1,
      httpOnly: false,
      secure: false,
      sameSite: "Lax" as const,
    })),
    origins: [],
  };
  fs.mkdirSync(path.dirname(E2E_AUTH_STATE_PATH), { recursive: true });
  fs.writeFileSync(E2E_AUTH_STATE_PATH, JSON.stringify(storageState, null, 2));
  fs.writeFileSync(E2E_AUTH_META_PATH, JSON.stringify({ userId: user.id }));

  // 6. 预清测试用户收藏（幂等），保证本次运行从空收藏态开始
  const cleanRes = await fetch(
    `${supabaseUrl}/rest/v1/user_style_favorites?user_id=eq.${user.id}`,
    { method: "DELETE", headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` } },
  );
  if (!cleanRes.ok) {
    console.warn(`[e2e] 预清测试用户收藏失败：HTTP ${cleanRes.status}（teardown 会重试）`);
  }

  console.log(
    `[e2e] 已登录 session 就绪：${E2E_TEST_USER_EMAIL}（cookie ${cookieChunks.length} 块，domain ${cookieDomain}）`,
  );
}

export default globalSetup;
