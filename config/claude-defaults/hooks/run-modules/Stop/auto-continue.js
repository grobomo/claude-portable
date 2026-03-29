// Auto-continue: check pending tasks, keep working
module.exports = function(input) {
  return {
    decision: "block",
    reason: "Check TODO.md for pending tasks. If tasks remain, do the next one. If all tasks are complete, think about what an expert dev would do next — clean up, optimize, test, document — and do it. Document your reasoning for future reference."
  };
};
