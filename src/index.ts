import fs from "node:fs";
import path from "node:path";
import { EOL } from "node:os";
import { generateApi } from "swagger-typescript-api";
import { camelize, stringifyObjectWithUnstringifiedKeys } from "./utils/text.js";
import { indentCharacter, indentCount } from "./config.js";

const result: Record<string, any> = {};
const runtimeDataResult: Record<string, any> = {};

let argFilePath = process.argv[2];
if (argFilePath === undefined)
  throw new Error('Missing filepath argument');
argFilePath = path.isAbsolute(argFilePath) ? argFilePath : path.resolve(process.cwd(), argFilePath);

if (!fs.existsSync(argFilePath))
  throw new Error('Specified schema file does not exist on your system');

generateApi({
  input: argFilePath,
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
    parser: "typescript",
  },
  cleanOutput: false,
  enumNamesAsValues: false,
  moduleNameFirstTag: false,
  generateUnionEnums: false,
  addReadonly: false,
  modular: true,
  fixInvalidTypeNamePrefix: "Type",
  fixInvalidEnumKeyPrefix: "Value",
  codeGenConstructs: (constructs) => {
    // console.log(constructs);

    return constructs;
  },
  primitiveTypeConstructs: (constructs) => ({
    ...constructs,
    string: {
      $default: 'string',
      "date-time": 'string',
    },
  }),
  hooks: {
    onCreateRoute: (routeData) => {

      const type = routeData.response.type;

      const routeParts = routeData.raw.route.split('/').filter(node => node.length);

      let currObj = result;
      let currObjRuntime = runtimeDataResult;

      let urlPathName: string;
      let camelCaseName: string;

      for(const el of routeParts) {
        camelCaseName = camelize(el);

        urlPathName = el.startsWith('{') ? camelCaseName : el;

        const normalizedName = camelCaseName.startsWith('{') ? camelCaseName.slice(1, -1) : camelCaseName;

        if (currObj[normalizedName] === undefined) {
          currObjRuntime[normalizedName] = {};
          currObj[normalizedName] = {};
        }
        currObj = currObj[normalizedName];
        currObjRuntime = currObjRuntime[normalizedName];
      }

      currObjRuntime.urlPath = urlPathName;
      currObjRuntime.method = routeData.raw.method.toUpperCase();
      currObj.result = type;
      // No query and path params (set params to undefined to allow generation of function with no arguments)
      if ((routeData.request as any).pathParams === undefined && (routeData.request as any).query === undefined)
        currObj.params = undefined;
      else { // Either query params or no query params, but path params exist, so use TEmptyReq - {}
        currObj.params = (((routeData.request as any).requestParams?.typeName) ?? 'TEmptyReq')
          + (` & {${EOL}${
            (routeData.request as any).parameters.map(({name, optional, type, description}) => `${indentCharacter.repeat(indentCount)}/** ${description} */${EOL}${indentCharacter.repeat(indentCount)}${name}${optional?'?':''}: ${type};${EOL}`).join(EOL)
          }}`);
      }

      return undefined;
    }
  },
})
  .then(({ files }) => {
    const dir = path.resolve(process.cwd(), "./generated");

    if (!fs.existsSync(dir))
      fs.mkdirSync(dir);

    // Create declarations file
    const outDeclarationsPath = path.resolve(dir, 'out.d.ts');
    fs.writeFileSync(outDeclarationsPath, 'type TEmptyReq = {}' + EOL, { encoding: 'utf8' });
    files.forEach(({ fileContent }) => {
      fs.appendFileSync(outDeclarationsPath, fileContent, { encoding: 'utf8' });
    });
    fs.appendFileSync(outDeclarationsPath, EOL + "type TWaxRestAPiExtended = " + stringifyObjectWithUnstringifiedKeys(['result','params'], {
      hafbe: result
    }, indentCount) + EOL + "declare var WaxExtendedData: TWaxRestAPiExtended" + EOL + "export default WaxExtendedData" + EOL, { encoding: 'utf8' });

    // Create runtime JS file
    const outSourcePath = path.resolve(dir, 'out.js');
    fs.writeFileSync(outSourcePath, "export default " + stringifyObjectWithUnstringifiedKeys([], {
      hafbe: runtimeDataResult
    }, indentCount) + EOL, { encoding: 'utf8' });
  })
  .catch((e) => {
    console.error(e);

    process.exitCode = 1;
  });
