import fs from "node:fs";
import path from "node:path";
import { Eta }from "eta";
import { fileEncoding }from "./constants.js";
import { makePathAbsolute }from "./utils/paths.js";

export interface INpmPackageConfig {
  outputDirectory: string;
  name: string;
  version: string;
  templatesDirectory: string;
  namespace?: string;
}

export const prepareNpmPackage = (config: INpmPackageConfig): void => {
  const displayName = config.namespace?.length > 0 ? `${config.namespace} API definitions` : config.name;
  const description = `Wax REST API definitions${(config.namespace.length > 0 ? " for " : "")}${(config.namespace || "")}`;
  const { name, version } = config;

  const packageJson = {
    name,
    version,
    description,
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

  const templatesDirectory = makePathAbsolute(config.templatesDirectory);

  const eta = new Eta({ views: templatesDirectory });
  const year = new Date().getFullYear();
  const etaData = { displayName, description, name, version, year };

  fs.writeFileSync(path.join(config.outputDirectory, "package.json"), JSON.stringify(packageJson, undefined, 2), { encoding: fileEncoding });

  fs.writeFileSync(path.join(config.outputDirectory, "README.md"), eta.render("./README.md.eta", etaData), { encoding: fileEncoding });
  fs.writeFileSync(path.join(config.outputDirectory, "LICENSE.md"), eta.render("./LICENSE.md.eta", etaData), { encoding: fileEncoding });
};
