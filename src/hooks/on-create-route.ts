import { type ParsedRoute } from "swagger-typescript-api";
import { EOL } from "node:os";
import { camelize } from "../utils/text.js";
import { indentCharacter, indentCount } from "../constants.js";

export const onCreateRoute = (result: Record<string, any>, runtimeDataResult: Record<string, any>, routeData: ParsedRoute) => {

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
};
