export const addNamespace = (obj: Record<string, any>, namespace?: string): Record<string, any> => {
  if (namespace !== undefined || namespace.length > 0)
    return {
      [namespace]: obj
    };

  return obj;
};
