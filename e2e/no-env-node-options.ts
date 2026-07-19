function tokenizeNodeOptions(value: string): string[] {
  const tokens: string[] = [];
  let token = "";
  let quote: '"' | "'" | undefined;

  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];

    if (quote) {
      if (character === quote) {
        quote = undefined;
      } else if (character === "\\" && index + 1 < value.length) {
        index += 1;
        token += value[index];
      } else {
        token += character;
      }
      continue;
    }

    if (character === '"' || character === "'") {
      quote = character;
    } else if (/\s/.test(character)) {
      if (token) {
        tokens.push(token);
        token = "";
      }
    } else {
      token += character;
    }
  }

  if (token) tokens.push(token);
  return tokens;
}

export function mergeNodeRequireOption(
  nodeOptions: string | undefined,
  preloadPath: string,
): string {
  const existing = nodeOptions ?? "";
  const tokens = tokenizeNodeOptions(existing);
  const alreadyPreloaded = tokens.some(
    (token, index) =>
      token === `--require=${preloadPath}` ||
      (token === "--require" && tokens[index + 1] === preloadPath),
  );

  if (alreadyPreloaded) return existing;

  const requireOption = `--require=${JSON.stringify(preloadPath)}`;
  return existing.trim() ? `${existing} ${requireOption}` : requireOption;
}
