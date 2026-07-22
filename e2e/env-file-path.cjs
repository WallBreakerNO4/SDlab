/* eslint-disable @typescript-eslint/no-require-imports -- CommonJS preload helper 由 blocker 直接 require */
const path = require("node:path");
const { fileURLToPath } = require("node:url");

function toLocalPath(filePath) {
  if (typeof filePath === "string") return filePath;
  if (Buffer.isBuffer(filePath)) return filePath.toString();
  if (filePath instanceof URL && filePath.protocol === "file:") {
    try {
      return fileURLToPath(filePath);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function isEnvFilePath(filePath) {
  const localPath = toLocalPath(filePath);
  if (localPath === undefined) return false;

  const basename = path.basename(localPath);
  return basename === ".env" || basename.startsWith(".env.");
}

module.exports = { isEnvFilePath };
