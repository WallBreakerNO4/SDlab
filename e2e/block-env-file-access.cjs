/* eslint-disable @typescript-eslint/no-require-imports -- NODE_OPTIONS --require 需要 CommonJS 预加载器 */
const fs = require("node:fs");
const fsPromises = require("node:fs/promises");
const path = require("node:path");
const { isEnvFilePath } = require("./env-file-path.cjs");

Reflect.set(
  globalThis,
  Symbol.for("sdlab.block-env-file-access.loaded"),
  true,
);

function envFileAccessError(filePath) {
  const error = new Error(`Environment file access blocked: ${path.basename(String(filePath))}`);
  error.code = "ENOENT";
  return error;
}

const originalExistsSync = fs.existsSync;
fs.existsSync = function existsSync(filePath) {
  return isEnvFilePath(filePath) ? false : originalExistsSync.call(this, filePath);
};

const originalReadFileSync = fs.readFileSync;
fs.readFileSync = function readFileSync(filePath, ...args) {
  if (isEnvFilePath(filePath)) throw envFileAccessError(filePath);
  return originalReadFileSync.call(this, filePath, ...args);
};

const originalReadFile = fs.readFile;
fs.readFile = function readFile(filePath, ...args) {
  if (isEnvFilePath(filePath)) {
    const callback = args.at(-1);
    if (typeof callback === "function") {
      queueMicrotask(() => callback(envFileAccessError(filePath)));
      return;
    }
    throw envFileAccessError(filePath);
  }
  return originalReadFile.call(this, filePath, ...args);
};

const originalPromisesReadFile = fsPromises.readFile;
fsPromises.readFile = async function readFile(filePath, ...args) {
  if (isEnvFilePath(filePath)) throw envFileAccessError(filePath);
  return originalPromisesReadFile.call(this, filePath, ...args);
};

if (typeof process.loadEnvFile === "function") {
  process.loadEnvFile = function loadEnvFile(filePath = ".env") {
    throw envFileAccessError(filePath);
  };
}
