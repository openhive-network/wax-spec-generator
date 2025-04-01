import { EOL } from "node:os";
import { indentCharacter, indentCount } from "../constants.js";

const reservedWords = new Set([
  "break",
  "case",
  "catch",
  "class",
  "const",
  "continue",
  "debugger",
  "default",
  "delete",
  "do",
  "else",
  "enum",
  "export",
  "extends",
  "false",
  "finally",
  "for",
  "function",
  "if",
  "import",
  "in",
  "instanceof",
  "let",
  "new",
  "null",
  "return",
  "super",
  "switch",
  "this",
  "throw",
  "true",
  "try",
  "typeof",
  "var",
  "void",
  "while",
  "with",
  "yield",
  "await",
  "abstract",
  "boolean",
  "byte",
  "char",
  "double",
  "final",
  "float",
  "goto",
  "int",
  "long",
  "native",
  "short",
  "synchronized",
  "throws",
  "transient",
  "volatile"
]);

export const ensureSafeKey = (key: string): string => {
  /*
   * Regular expression criteria for valid unquoted identifiers
   * It should start with a letter, underscore, or dollar sign
   * Followed by any word character (letter, digit, underscore)
   */
  const validIdentifierRegex = /^[a-zA-Z_$][\w$]*$/;

  // Check for reserved words or invalid identifier pattern
  if (reservedWords.has(key) || !validIdentifierRegex.test(key))
    return `"${key}"`;

  return key;
};

export const camelize = (str: string): string => str.replace(/-./g, node => node[1].toUpperCase());

export const stringifyObjectWithUnstringifiedKeys = (keys: string[], obj: any, lastIndentation = 0): string => {
  if (typeof obj !== "object")
    return JSON.stringify(obj).replaceAll(EOL, indentCharacter.repeat(lastIndentation) + EOL);

  let json = `{${  EOL}`;

  const keysInObj = Object.keys(obj);
  for (let i = 0; i < keysInObj.length; ++i) {
    if (i > 0)
      json += `,${  EOL}`;

    json += `${indentCharacter.repeat(lastIndentation)  }${ensureSafeKey(keysInObj[i])}: `;

    if (keys.includes(keysInObj[i]))
      json += String(obj[keysInObj[i]]).replaceAll(EOL, EOL + indentCharacter.repeat(lastIndentation));
    else
      json += stringifyObjectWithUnstringifiedKeys(keys, obj[keysInObj[i]], lastIndentation + indentCount);
  }

  return `${json + EOL + indentCharacter.repeat(lastIndentation - indentCount)  }}`;
};
