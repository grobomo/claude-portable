# Hooks Must Be Synchronous

- Use `fs.readFileSync(0, "utf-8")` for stdin — NEVER `process.stdin.on`
- Async hooks race with the timeout and silently fail
- All modules export a synchronous function: `module.exports = function(input) {}`
