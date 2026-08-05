import { EOL } from "node:os";
import { type ParsedRoute } from "swagger-typescript-api";
import { indentCharacter, indentCount } from "../constants.js";
import { camelize } from "../utils/text.js";

export const onCreateRoute = (
  apiType: "jsonrpc" | "rest",
  shouldCamelize: boolean,
  result: Record<string, any>,
  runtimeDataResult: Record<string, any>,
  routeData: ParsedRoute
): undefined => {
  const { type } = routeData.response;

  const isRestApi = apiType === "rest";

  const rawRoute = routeData.raw.route;
  const routeParts = rawRoute.split(isRestApi ? "/" : ".").filter(node => node.length);

  /*
   * A trailing slash marks a distinct "directory" resource: `/x/` is not the same resource as the
   * item `/x`, and it must not clobber the container node that parents `/x/...` child routes.
   * `filter(node => node.length)` above drops the empty segment the slash produces, so we track it
   * separately here.
   */
  const hasTrailingSlash = isRestApi && routeParts.length > 0 && rawRoute.endsWith("/");

  let currObj = result;
  let currObjRuntime = runtimeDataResult;

  let urlPathName = "";

  for (let i = 0; i < routeParts.length; ++i) {
    const el = routeParts[i];
    const isDirectoryEndpoint = i === routeParts.length - 1 && hasTrailingSlash;

    const camelCaseName = shouldCamelize ? camelize(el) : el;
    urlPathName = el.startsWith("{") ? camelCaseName : el;
    const baseName = camelCaseName.startsWith("{") ? camelCaseName.slice(1, -1) : camelCaseName;

    let key: string;
    let nodeUrlPath: string;

    if (isDirectoryEndpoint) {
      /*
       * Directory endpoint `/x/`. Inline it on a fresh node so a lone `/x/` stays a clean `.x` whose
       * urlPath keeps the slash; if the plain node is already taken by the item/container `/x`, put
       * the directory on a dedicated `x/` sibling instead. The decision keys off the INCOMING route
       * being a directory - not the existing node - so an item never lands on the `x/` sibling.
       */
      key = currObj[baseName] === undefined ? baseName : `${baseName}/`;
      nodeUrlPath = `${urlPathName}/`;
    } else {
      /*
       * Item or intermediate container. This node must stay a slash-less container so child routes
       * join cleanly (no `x//y`). If a lone `/x/` was previously inlined here it is a pure leaf, so
       * evict that directory endpoint onto a `x/` sibling and reset this node. Reconciling here keeps
       * the whole scheme order independent - it does not matter whether `/x`, `/x/` or `/x/y` is seen
       * first.
       */
      if (currObj[baseName] !== undefined && currObjRuntime[baseName].urlPath.endsWith("/")) {
        currObjRuntime[`${baseName}/`] = currObjRuntime[baseName];
        currObj[`${baseName}/`] = currObj[baseName];
        currObjRuntime[baseName] = { urlPath: urlPathName };
        currObj[baseName] = {};
      }
      key = baseName;
      nodeUrlPath = urlPathName;
    }

    if (currObj[key] === undefined) {
      currObjRuntime[key] = {
        urlPath: nodeUrlPath
      };
      currObj[key] = {};
    }
    currObj = currObj[key];
    currObjRuntime = currObjRuntime[key];
  }

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
      (routeData.request as any).parameters.map(
        (node: { description: string; name: string; optional: boolean; type: string }) => `${
          indentCharacter.repeat(indentCount)
        }/** ${node.description} */${EOL}${
          indentCharacter.repeat(indentCount) + node.name + (node.optional ? "?" : "")
        }: ${node.type};${EOL}`).join(EOL)
    }}`;

  return undefined;
};
