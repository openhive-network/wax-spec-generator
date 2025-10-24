import { camelize } from "./text.js";

export const addNamespace = (obj: Record<string, any>, shouldCamelize: boolean, namespace?: string, isRuntime: boolean = false): Record<string, any> => {
  if (namespace !== undefined && namespace.length > 0)
    return isRuntime ? {
      [shouldCamelize ? camelize(namespace) : namespace]: obj,
      urlPath: namespace
    } : {
      [shouldCamelize ? camelize(namespace) : namespace]: obj
    };

  return obj;
};
