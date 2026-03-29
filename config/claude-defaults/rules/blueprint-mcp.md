# Blueprint MCP Usage Rules

## No Sleep Between Actions
- NEVER use `sleep` between Blueprint MCP calls. Each Claude prompt takes 3-10 seconds to process, which is more than enough time for pages to load.
- Just call the next Blueprint action directly — the page will have loaded by the time the tool executes.
- The sleep wastes time twice: once for the sleep itself, once for Claude processing the sleep result.

## Tab Detachment
- SharePoint and other SSO-heavy sites frequently cause tab detachment during navigation/clicks.
- After any click that triggers navigation, check if the tab is still attached before the next action. If you get a "No tab attached" or "Detached" error, reattach with `browser_tabs action='attach'`.
- Use `browser_evaluate` with JavaScript for clicking elements that `browser_interact` can't reach (shadow DOM, overlays, dynamically rendered buttons).

## SharePoint Stream Pages
- ALWAYS open each SharePoint recording in a NEW tab (`browser_tabs action='new'`). Never reuse/navigate within an existing Stream tab — the SPA gets stuck on a loading spinner.
- Close the tab after the download completes to avoid tab accumulation.
- The Transcript panel loads below the viewport. Use `browser_evaluate` to click elements, not coordinates.
