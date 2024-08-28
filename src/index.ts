import fs from "node:fs";
import path from "node:path";
import url from 'node:url'
import { EOL } from "node:os";
import { generateApi } from "swagger-typescript-api";
import { camelize, stringifyObjectWithUnstringifiedKeys } from "./utils/text.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))

const result: Record<string, any> = {};
const runtimeDataResult: Record<string, any> = {};

/* NOTE: all fields are optional expect one of `input`, `url`, `spec` */
generateApi({
  input: path.resolve(process.cwd(), "./data/hafbe.json"),
  templates: path.resolve(__dirname, "../src/templates"),
  /*extraTemplates: [
    {
      name: 'interface-data-contract.ejs',
      path: path.resolve(__dirname, "../src/templates/base/interface-data-contract.ejs")
    }
  ],*/
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
    onCreateComponent: (component) => {
      // console.log(component);

      return undefined;
    },
    onCreateRequestParams: (rawType) => {
      // console.log(rawType);

      return undefined;
    },
    onCreateRoute: (routeData) => {

      const type = routeData.response.type;

      const routeParts = routeData.raw.route.split('/').filter(node => node.length);

      let currObj = result;
      let currObjRuntime = runtimeDataResult;

      let camelCaseName: string;

      for(const el of routeParts) {
        camelCaseName = camelize(el);

        const normalizedName = camelCaseName.startsWith('{') ? camelCaseName.slice(1, -1) : camelCaseName;

        if (currObj[normalizedName] === undefined) {
          currObjRuntime[normalizedName] = {};
          currObj[normalizedName] = {};
        }
        currObj = currObj[normalizedName];
        currObjRuntime = currObjRuntime[normalizedName];
      }

      currObjRuntime.urlPath = camelCaseName;
      currObjRuntime.method = routeData.raw.method.toUpperCase();
      currObj.result = type;
      currObj.params = undefined;

      return undefined;
    },
    onCreateRouteName: (routeNameInfo, rawRouteInfo) => {
      // console.log(routeNameInfo, rawRouteInfo);

      // console.log((rawRouteInfo.responses?.[200] as any).content);

      return undefined;
    },
    onFormatRouteName: (routeInfo, templateRouteName) => {
      // console.log(routeInfo, templateRouteName);
      // hafbe_endpoints.get_latest_blocks -> /operation-type-counts

      return undefined;
    },
    onFormatTypeName: (typeName, rawTypeName, schemaType) => {
      // console.log(typeName, rawTypeName, schemaType);
      // HafbeEndpointsGetWitnessesParams -> HafbeEndpointsGetWitnessesParams
      // hafbe_types.account_authority -> HafbeTypesAccountAuthority

      return undefined;
    },
    onInit: (configuration) => undefined,
    onPreParseSchema: (originalSchema, typeName, schemaType) => {
      // console.log(originalSchema, typeName, schemaType);

      return undefined;
    },
    onParseSchema: (originalSchema, parsedSchema) => {
      // console.log(originalSchema, parsedSchema);

      return undefined;
    },
    onBuildRoutePath: (data) => {
      // console.log(data); // { originalRoute, route, pathParams }

      return undefined;
    },
    onInsertPathParam: (paramName, index, arr, resultRoute) => {
      // console.log(paramName, index, arr, resultRoute); // inputValue 0 [{ $match: '{input-value}', name: 'inputValue', type: 'string' }] /input-type/{input-value}

      return undefined;
    },
    onPreBuildRoutePath: (routePath) => {
      // console.log(routePath); // /input-type/{input-value}

      return undefined;
    },
    onPrepareConfig: (currentConfiguration) => {
      // currentConfiguration.config.templatePaths

      return undefined;
    },
  },
})
  .then(({ files, configuration }) => {
    const outDeclarationsPath = path.resolve(process.cwd(), "./generated/out.d.ts");
    fs.writeFileSync(outDeclarationsPath, '', { encoding: 'utf8' });
    files.forEach(({ fileContent }) => {
      fs.appendFileSync(outDeclarationsPath, fileContent, { encoding: 'utf8' });
    });
    fs.appendFileSync(outDeclarationsPath, EOL + "type TWaxRestAPiExtended = " + stringifyObjectWithUnstringifiedKeys(['result','params'], {
      hafbe: result
    }, 2, 2) + EOL + "declare var WaxExtendedData: TWaxRestAPiExtended" + EOL + "export default WaxExtendedData" + EOL, { encoding: 'utf8' });

    const outSourcePath = path.resolve(process.cwd(), "./generated/out.js");
    fs.writeFileSync(outSourcePath, "export default " + stringifyObjectWithUnstringifiedKeys([], {
      hafbe: runtimeDataResult
    }, 2, 2) + EOL, { encoding: 'utf8' });
  })
  .catch((e) => {
    console.error(e);

    process.exitCode = 1;
  });
