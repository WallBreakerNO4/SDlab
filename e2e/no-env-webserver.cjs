/**
 * no-env e2e 的 webServer 启动器。
 *
 * 先启动假 Supabase REST 端点（构建期与运行期的服务端查询都依赖它），再依次执行
 * `next build` 与 `next start`。Playwright 结束时会终止本进程；这里负责把信号转发
 * 给 Next 子进程并关闭假端点，避免残留监听端口。
 */
/* eslint-disable @typescript-eslint/no-require-imports -- no-env e2e 的 CommonJS 启动器 */
const path = require("node:path");
const { spawn } = require("node:child_process");

const { startMockSupabaseRestServer } = require("./mock-supabase-rest.cjs");

const PORT = process.env.E2E_PORT ?? "3100";
const MOCK_SUPABASE_PORT = Number(process.env.E2E_MOCK_SUPABASE_PORT ?? "3199");
const NEXT_CLI = path.resolve(__dirname, "..", "node_modules/.bin/next");

let nextProcess = null;
let shuttingDown = false;

function shutdown(exitCode) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (nextProcess && nextProcess.exitCode === null) {
    nextProcess.kill("SIGTERM");
  }
  process.exit(exitCode);
}

function runNext(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(NEXT_CLI, args, { stdio: "inherit", env: process.env });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(code ?? 1);
    });
  });
}

async function main() {
  await startMockSupabaseRestServer({ port: MOCK_SUPABASE_PORT });
  console.log(`[no-env] mock supabase REST listening on 127.0.0.1:${MOCK_SUPABASE_PORT}`);

  const buildExitCode = await runNext(["build"]);
  if (buildExitCode !== 0) {
    shutdown(buildExitCode);
    return;
  }

  nextProcess = spawn(NEXT_CLI, ["start", "-p", PORT], {
    stdio: "inherit",
    env: process.env,
  });
  nextProcess.once("exit", (code) => shutdown(code ?? 0));
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => shutdown(0));
}

main().catch((error) => {
  console.error("[no-env] failed to start web server:", error);
  shutdown(1);
});
