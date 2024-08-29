import path from "node:path";

export const makePathAbsolute = (inputFile: string) => path.isAbsolute(inputFile) ? inputFile : path.resolve(process.cwd(), inputFile);
