import { EOL } from "node:os";
import { indentCharacter, indentCount } from "../config.js";

export const camelize = (str: string) => str.replace(/-./g, node => node[1].toUpperCase());

export const stringifyObjectWithUnstringifiedKeys = (keys: string[], obj: any, lastIndentation = 0): string => {
  if (typeof obj !== "object")
    return JSON.stringify(obj).replaceAll(EOL, indentCharacter.repeat(lastIndentation) + EOL);

  let json = "{" + EOL;

  const keysInObj = Object.keys(obj);
  for(let i = 0; i < keysInObj.length; ++i) {
    if (i > 0)
      json += "," + EOL;

    json += indentCharacter.repeat(lastIndentation) + `${keysInObj[i]}: `;

    if (keys.includes(keysInObj[i]))
      json += String(obj[keysInObj[i]]).replaceAll(EOL, EOL + indentCharacter.repeat(lastIndentation));
    else
      json += stringifyObjectWithUnstringifiedKeys(keys, obj[keysInObj[i]], lastIndentation + indentCount);
  }

  return json + EOL + indentCharacter.repeat(lastIndentation - indentCount) + "}";
};
