import fs from "node:fs";
import { EOL }from "node:os";
import path from "node:path";
import { generateApi }from "swagger-typescript-api";
import { fileEncoding, indentCount }from "./constants.js";
import { onCreateRoute }from "./hooks/on-create-route.js";
import { addNamespace }from "./utils/object.js";
import { stringifyObjectWithUnstringifiedKeys }from "./utils/text.js";

export interface IGeneratorConfig {
  inputFile: string;
  outputDirectory: string;
  /**
   * @default "index"
   */
  outputFilePrefix?: string;
  namespace?: string;
}

export const generate = async(config: IGeneratorConfig): Promise<void> => {
  config.outputFilePrefix ??= "index";

  const result: Record<string, any> = {};
  const runtimeDataResult: Record<string, any> = {};

  if (!fs.existsSync(config.inputFile))
    throw new Error("Specified schema file does not exist on your system");

  const { files } = await generateApi({
    input: config.inputFile,
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
      onCreateRoute: onCreateRoute.bind(undefined, result, runtimeDataResult)
    }
  });

  // Create declarations file
  const outDeclarationsPath = path.join(config.outputDirectory, `${config.outputFilePrefix}.d.ts`);
  fs.writeFileSync(outDeclarationsPath, `type TEmptyReq = {}${  EOL}`, { encoding: fileEncoding });
  files.forEach(({ fileContent }) => {
    fs.appendFileSync(outDeclarationsPath, fileContent, { encoding: fileEncoding });
  });
  fs.appendFileSync(
    outDeclarationsPath,
    `${EOL  }type TWaxRestAPiExtended = ${
      stringifyObjectWithUnstringifiedKeys([ "result", "params" ], addNamespace(result, config.namespace, false), indentCount)
    }${EOL  }declare var WaxExtendedData: TWaxRestAPiExtended${  EOL  }export default WaxExtendedData${  EOL}`,
    { encoding: fileEncoding }
  );

  // Create runtime JS file
  const outSourcePath = path.join(config.outputDirectory, `${config.outputFilePrefix}.js`);
  fs.writeFileSync(
    outSourcePath,
    `export default ${  stringifyObjectWithUnstringifiedKeys([], addNamespace(runtimeDataResult, config.namespace, true), indentCount)  }${EOL}`,
    { encoding: fileEncoding }
  );
};
