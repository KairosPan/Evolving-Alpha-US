/** Small, pure translations for the bot settings page. */

// The settings endpoint currently accepts this exact provider/model grammar.
const MODEL_ROUTE = /^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.:-]*$/;

/** Validate the route accepted by the bot settings endpoint.
 * @param {string} value @returns {string|null} */
export function normalizeBotModel(value) {
  const route = value.trim();
  if (route === "") return null;
  if (!MODEL_ROUTE.test(route)) throw new Error("Use provider/model (one slash, no spaces), or leave the model empty to inherit the default.");
  return route;
}

/** @param {any} catalog @returns {{value: string, label: string}[]} */
export function botModelChoices(catalog) {
  const choices = new Map();
  for (const group of Array.isArray(catalog?.groups) ? catalog.groups : []) {
    if (typeof group?.id !== "string") continue;
    for (const model of Array.isArray(group.models) ? group.models : []) {
      if (typeof model?.id !== "string") continue;
      const value = `${group.id}/${model.id}`;
      if (!MODEL_ROUTE.test(value)) continue;
      choices.set(value, { value, label: `${group.name || group.id} · ${model.name || model.id}` });
    }
  }
  return [...choices.values()];
}

/** @param {Record<string, string>} fields @returns {string} */
export function draftBotSoul(fields) {
  const sections = [
    ["Identity and perspective", fields.identity],
    ["Questions I focus on", fields.focus],
    ["Evidence I require", fields.evidence],
    ["What changes my mind", fields.revise],
    ["When I speak or pass", fields.participation],
    ["Communication style", fields.style],
  ];
  return sections.filter(([, text]) => text?.trim()).map(([title, text]) => `## ${title}\n\n${text.trim()}`).join("\n\n");
}

const TOOL_LABELS = {
  ask_user_question: "Ask the operator", bash: "Terminal", edit: "Edit files", glob: "Find files",
  grep: "Search file contents", read: "Read files", read_image: "Inspect images", skill: "Load skills",
  str_replace_editor: "Replace file text", web_search: "Search the web", write: "Write files",
  earnings: "Earnings", daily_bars: "Daily prices", calendar: "Trading calendar", corp_actions: "Corporate actions",
  market_snapshot: "Market snapshots", screen: "Stock screening", breadth: "Market breadth",
};

/** The raw pattern stays visible in the UI; labels never imply access is granted.
 * @param {string} pattern @returns {string} */
export function botToolLabel(pattern) {
  const key = pattern.startsWith("mcp__") ? pattern.split("__").at(-1) : pattern;
  return TOOL_LABELS[key] ?? pattern;
}

/** @param {Record<string, any>} bot @param {{name:string, description:string, model:string, soul:string}} fields */
export function botSettingsPayload(bot, fields) {
  return {
    id: bot.id,
    revision: bot.revision,
    name: fields.name.trim(),
    description: fields.description.trim(),
    model: normalizeBotModel(fields.model),
    soul: fields.soul,
  };
}
