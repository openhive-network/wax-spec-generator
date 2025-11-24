import fs from "node:fs";
import { EOL } from "node:os";
import path from "node:path";
import { generateApi } from "swagger-typescript-api";
import { fileEncoding, indentCount } from "./constants.js";
import { onCreateRoute } from "./hooks/on-create-route.js";
import { addNamespace } from "./utils/object.js";
import { makePathAbsolute } from "./utils/paths.js";
import { stringifyObjectWithUnstringifiedKeys } from "./utils/text.js";
import { compile } from "./utils/typescript.js";

export interface IGeneratorConfig {
  apiType: "jsonrpc" | "rest";
  input: string;
  outputDirectory: string;
  /**
   * @default "index"
   */
  outputFilePrefix?: string;
  camelize: boolean;
  namespace?: string;
}

export const generate = async(config: IGeneratorConfig): Promise<void> => {
  config.outputFilePrefix ??= "index";

  const result: Record<string, any> = {};
  const runtimeDataResult: Record<string, any> = {};

  let inputFileOrUrl: { input: string } | { url: string } | null = null;

  if (fs.existsSync(config.input))
    inputFileOrUrl = { input: makePathAbsolute(config.input) };
  else if (config.input.startsWith("http://") || config.input.startsWith("https://"))
    inputFileOrUrl = { url: config.input };
  else
    throw new Error("Specified schema file does not exist on your system");


  const { files } = await generateApi({
    ...inputFileOrUrl,
    generateClient: false,
    generateRouteTypes: false,
    generateResponses: true,
    extractRequestParams: true,
    extractRequestBody: true,
    extractEnums: true,
    prettier: {
      printWidth: 120,
      tabWidth: 2,
      trailingComma: "all",
      parser: "typescript"
    },
    cleanOutput: false,
    enumNamesAsValues: false,
    moduleNameFirstTag: false,
    generateUnionEnums: false,
    addReadonly: false,
    modular: true,
    fixInvalidTypeNamePrefix: "Type",
    fixInvalidEnumKeyPrefix: "Value",
    primitiveTypeConstructs: constructs => ({
      ...constructs,
      string: {
        "$default": "string",
        "date-time": "string"
      }
    }),
    hooks: {
      onCreateRoute: onCreateRoute.bind(undefined, config.apiType, config.camelize, result, runtimeDataResult)
    }
  });

  let tempTypeScriptSource = "";

  tempTypeScriptSource += `type TEmptyReq = {}${EOL}`;
  files.forEach(({ fileContent }) => {
    const normalizedDeclarationsContent = fileContent.replace(/([:=,|([&<>]\s*)\bobject\b/g, "$1Record<string, any>");

    tempTypeScriptSource += normalizedDeclarationsContent;
  });
  tempTypeScriptSource += `${EOL}export default ${stringifyObjectWithUnstringifiedKeys(
    [],
    addNamespace(runtimeDataResult, config.camelize, config.namespace, true),
    indentCount
  )} as unknown as ${
    stringifyObjectWithUnstringifiedKeys([ "result", "params" ], addNamespace(result, config.camelize, config.namespace, false), indentCount)
  };${EOL}`;

  const compiledCode = compile(tempTypeScriptSource);

  const outDeclarationsPath = path.join(config.outputDirectory, `${config.outputFilePrefix}.d.ts`);
  const outSourcePath = path.join(config.outputDirectory, `${config.outputFilePrefix}.js`);

  fs.writeFileSync(
    outDeclarationsPath,
    compiledCode.dts,
    { encoding: fileEncoding }
  );

  fs.writeFileSync(
    outSourcePath,
    compiledCode.js,
    { encoding: fileEncoding }
  );
};
