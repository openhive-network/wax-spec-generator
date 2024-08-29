#!/usr/bin/env node
import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import path from "node:path";
import { generate } from "./generator.js";
import { makePathAbsolute } from "./utils/paths.js";
import { prepareNpmPackage } from "./npm.js";

const argv = await yargs(hideBin(process.argv))
  .option("namespace", {
    alias: "N",
    type: "string",
    description: "Optional namespace name for the application - adds a nested level of object with given namespace name for all of the parsed API definitions",
    default: ""
  })
  .option("input-file", {
    alias: "i",
    type: "string",
    description: "Swagger JSON schema input file",
    demandOption: true
  })
  .option("output-directory", {
    alias: "o",
    type: "string",
    description: "Output directory for the generated files to be saved",
    default: "generated"
  })
  .option("emit-npm-project", {
    alias: "e",
    type: "boolean",
    description: "When enabled, generates package.json file in the output directory, for the project to be pushed",
    default: false
  })
  .option("npm-name", {
    type: "string",
    description: "Name of the generated npm project - required when --emit-npm-project option is set"
  })
  .option("npm-license-file", {
    type: "string",
    description: "Path to the license file to be copied inside the generated npm project. Supports ETA syntax",
    default: "./LICENSE.md"
  })
  .option("npm-readme-file", {
    type: "string",
    description: "Path to the README file to be copied inside the generated npm project. Supports ETA syntax",
    default: "./readme-for-generated.md"
  })
  .option("npm-version", {
    type: "string",
    description: "Version of the generated npm project - required when --emit-npm-project option is set"
  })
  .parse();

const inputFile = makePathAbsolute(argv.inputFile);
const outputDirectory = makePathAbsolute(argv.outputDirectory);

if (argv.emitNpmProject) {
  if (argv.npmName === undefined || argv.npmVersion === undefined)
    throw new Error("Trying to create npm project without npm package name and/or version");

  prepareNpmPackage({
    outputDirectory,
    version: argv.npmVersion,
    name: argv.npmName,
    namespace: argv.namespace
  });
}

await generate({
  inputFile,
  outputDirectory,
  namespace: argv.namespace
});
