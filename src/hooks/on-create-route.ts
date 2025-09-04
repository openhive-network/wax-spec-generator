import { EOL } from "node:os";
import { type ParsedRoute } from "swagger-typescript-api";
import { indentCharacter, indentCount } from "../constants.js";
import { camelize } from "../utils/text.js";

export const onCreateRoute = (
  apiType: "jsonrpc" | "rest",
  result: Record<string, any>,
  runtimeDataResult: Record<string, any>,
  routeData: ParsedRoute
): undefined => {
  const { type } = routeData.response;

  const isRestApi = apiType === "rest";

  const routeParts = routeData.raw.route.split(isRestApi ? "/" : ".").filter(node => node.length);

  let currObj = result;
  let currObjRuntime = runtimeDataResult;

  let urlPathName: string;
  let camelCaseName: string;

  for (const el of routeParts) {
    camelCaseName = camelize(el);

    urlPathName = el.startsWith("{") ? camelCaseName : el;

    const normalizedName = camelCaseName.startsWith("{") ? camelCaseName.slice(1, -1) : camelCaseName;

    if (currObj[normalizedName] === undefined) {
      currObjRuntime[normalizedName] = {
        urlPath: urlPathName
      };
      currObj[normalizedName] = {};
    }
    currObj = currObj[normalizedName];
    currObjRuntime = currObjRuntime[normalizedName];
  }

  currObjRuntime.urlPath = urlPathName;
  currObjRuntime.method = routeData.raw.method.toUpperCase();
  currObj.result = type;
  // No query and path params (set params to undefined to allow generation of function with no arguments)
  if ( (routeData.request as any).pathParams === undefined
    && (routeData.request as any).query === undefined
    && (routeData.request as any).payload?.type === undefined)
    currObj.params = undefined;
  else // Either query params or no query params, but path params exist, so use TEmptyReq - {}
    currObj.params = `${((routeData.request as any).requestParams?.typeName) ?? "TEmptyReq"
    } & ${(routeData.request as any).payload?.type ?? "TEmptyReq"
    } & {${EOL}${
      (routeData.request as any).parameters.map(node => `${indentCharacter.repeat(indentCount)}/** ${node.description} */${EOL}${
        indentCharacter.repeat(indentCount) + node.name + (node.optional ? "?" : "")
      }: ${node.type};${EOL}`).join(EOL)
    }}`;

  return undefined;
};
