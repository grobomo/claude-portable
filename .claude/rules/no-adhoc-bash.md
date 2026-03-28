# No Ad-hoc Bash for Fleet Operations

Never SSH into workers or run one-off bash loops to manage the fleet.
Always use `ccc` commands. If a command doesn't exist, build it first.
Examples: `ccc maint --all`, `ccc work`, `ccc board`, `ccc interrupt`.
