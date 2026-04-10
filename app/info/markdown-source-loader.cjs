module.exports = function markdownSourceLoader(source) {
  return `export default ${JSON.stringify(source)};`;
};
