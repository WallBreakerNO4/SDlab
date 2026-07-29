module.exports = function markdownSourceLoader(source) {
  const isModelGuide = /[\\/]data[\\/]model-guides[\\/]/i.test(this.resourcePath || "");
  if (isModelGuide) {
    const match = source.match(/^\uFEFF?---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)([\s\S]*)$/);
    if (!match) {
      throw new Error(`${this.resourcePath}: missing YAML frontmatter`);
    }
    source = match[1].replace(/^\r?\n/, "");
  }
  return `export default ${JSON.stringify(source)};`;
};
