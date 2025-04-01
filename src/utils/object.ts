import { camelize } from "./text.js";

export const addNamespace = (obj: Record<string, any>, namespace?: string, isRuntime: boolean = false): Record<string, any> => {
  if (namespace !== undefined && namespace.length > 0)
    return isRuntime ? {
      [camelize(namespace)]: obj,
      urlPath: namespace
    } : {
      [camelize(namespace)]: obj
    };

  return obj;
};
