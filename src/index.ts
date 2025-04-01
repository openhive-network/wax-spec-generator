#!/usr/bin/env node
import fs from "node:fs";
import { generate } from "./generator.js";
import { prepareNpmPackage } from "./npm.js";
import { parseOptions } from "./parse-options.js";
import { parseNamespace } from "./utils/namespace.js";
import { makePathAbsolute } from "./utils/paths.js";

const argv = await parseOptions();

const inputFile = makePathAbsolute(argv.inputFile);
const outputDirectory = makePathAbsolute(argv.outputDirectory);

if (!fs.existsSync(outputDirectory))
  fs.mkdirSync(outputDirectory);

const namespace = argv.namespace ?? parseNamespace(inputFile);

if (argv.emitNpmProject) {
  if (argv.npmName === undefined || argv.npmVersion === undefined)
    throw new Error("Trying to create npm project without npm package name and/or version");

  prepareNpmPackage({
    outputDirectory,
    version: argv.npmVersion,
    name: argv.npmName,
    namespace,
    templatesDirectory: argv.templatesDirectory
  });
}

await generate({
  inputFile,
  outputDirectory,
  namespace
});
