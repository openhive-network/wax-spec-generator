import { EOL } from "node:os";

export const camelize = (str: string) => str.replace(/-./g, node => node[1].toUpperCase());

export const stringifyObjectWithUnstringifiedKeys = (keys: string[], obj: any, indentLines = 2, lastIndentation = 0): string => {
  if (typeof obj !== "object")
    return JSON.stringify(obj);

  let json = "{" + EOL;

  const keysInObj = Object.keys(obj);
  for(let i = 0; i < keysInObj.length; ++i) {
    if (i > 0)
      json += "," + EOL;

    json += " ".repeat(lastIndentation) + `${keysInObj[i]}: `;

    if (keys.includes(keysInObj[i]))
      json += obj[keysInObj[i]];
    else
      json += stringifyObjectWithUnstringifiedKeys(keys, obj[keysInObj[i]], indentLines, lastIndentation + indentLines);
  }

  return json + EOL + " ".repeat(lastIndentation - indentLines) + "}";
};
