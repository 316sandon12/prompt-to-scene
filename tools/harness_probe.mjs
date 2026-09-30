// Mount only in an isolated test profile. Exercises the actual Harness ToolRuntime.
import fs from 'node:fs';
export const name = 'pts-native-probe';
export const inject = ['tools'];
export function apply(ctx) {
  let attempts = 0, busy = false;
  const timer = setInterval(async () => {
    if (busy) return;
    busy = true;
    try {
      const result = await ctx.tools.execute({
        callId: 'pts-probe', name: 'mcp__prompt_to_scene__list_projects',
        arguments: {}, signal: new AbortController().signal,
      });
      if (result.isError && attempts++ < 20) { busy = false; return; }
      // Only persist validation metadata; discovered user project paths stay private.
      fs.writeFileSync(process.env.PTS_PROBE_RESULT, JSON.stringify({
        passed: !result.isError, tool: 'mcp__prompt_to_scene__list_projects',
      }));
      clearInterval(timer);
      process.exit(result.isError ? 1 : 0);
    } catch (error) {
      if (attempts++ < 20) { busy = false; return; }
      fs.writeFileSync(process.env.PTS_PROBE_RESULT, JSON.stringify({passed: false, error: String(error)}));
      clearInterval(timer);
      process.exit(1);
    }
  }, 1000);
  ctx.effect(() => () => clearInterval(timer));
}
