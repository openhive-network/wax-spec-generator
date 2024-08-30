#!/usr/bin/env node
import fs from "node:fs";
import { generate } from "./generator.js";
import { makePathAbsolute } from "./utils/paths.js";
import { prepareNpmPackage } from "./npm.js";
import { parseOptions } from "./parse-options.js";

const argv = await parseOptions();

const inputFile = makePathAbsolute(argv.inputFile);
const outputDirectory = makePathAbsolute(argv.outputDirectory);

if (!fs.existsSync(outputDirectory))
  fs.mkdirSync(outputDirectory);

if (argv.emitNpmProject) {
  if (argv.npmName === undefined || argv.npmVersion === undefined)
    throw new Error("Trying to create npm project without npm package name and/or version");

  prepareNpmPackage({
    outputDirectory,
    version: argv.npmVersion,
    name: argv.npmName,
    namespace: argv.namespace,
    templatesDirectory: argv.templatesDirectory
  });
}

await generate({
  inputFile,
  outputDirectory,
  namespace: argv.namespace
});
