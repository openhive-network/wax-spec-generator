#!/usr/bin/env node
import fs from "node:fs";
import { generate } from "./generator.js";
import { prepareNpmPackage } from "./npm.js";
import { parseOptions } from "./parse-options.js";
import { makePathAbsolute } from "./utils/paths.js";

const argv = await parseOptions();

const outputDirectory = makePathAbsolute(argv.outputDirectory);

if (!fs.existsSync(outputDirectory))
  fs.mkdirSync(outputDirectory);

const apiType = argv.apiType as "jsonrpc" | "rest";

if (argv.emitNpmProject) {
  if (argv.npmName === undefined || argv.npmVersion === undefined)
    throw new Error("Trying to create npm project without npm package name and/or version");

  prepareNpmPackage({
    apiType,
    outputDirectory,
    version: argv.npmVersion,
    name: argv.npmName,
    namespace: argv.addNamespace,
    templatesDirectory: argv.templatesDirectory
  });
}

await generate({
  apiType,
  input: argv.input,
  outputDirectory,
  namespace: argv.addNamespace,
  camelize: argv.camelize
});
