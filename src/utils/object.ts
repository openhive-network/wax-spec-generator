export const addNamespace = (obj: Record<string, any>, namespace?: string): Record<string, any> => {
  if (namespace !== undefined)
    return {
      [namespace]: obj
    };

  return obj;
};
