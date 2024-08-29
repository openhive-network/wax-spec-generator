import fs from "node:fs";
import path from "node:path";
import { fileEncoding } from "./constants.js";

export interface INpmPackageConfig {
  outputDirectory: string;
  name: string;
  version: string;
  namespace?: string;
}

export const prepareNpmPackage = (config: INpmPackageConfig): void => {
  const packageJson = {
    name: config.name,
    version: config.version,
    description: `Wax REST API definitions${(config.namespace.length > 0 ? " for " : "")}${(config.namespace || "")}`,
    main: "./index.js",
    types: "./index.d.ts",
    private: false,
    type: "module",
    license: "SEE LICENSE IN LICENSE.md",
    exports: {
      ".": {
        default: {
          import: {
            types: "./index.d.ts",
            default: "./index.js"
          }
        }
      },
      "./package.json": "./package.json"
    },
    files: [
      "index.js",
      "index.d.ts"
    ]
  };

  fs.writeFileSync(path.join(config.outputDirectory, "package.json"), JSON.stringify(packageJson, undefined, 2), { encoding: fileEncoding });
};
