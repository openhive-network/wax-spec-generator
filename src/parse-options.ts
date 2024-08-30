import yargs from "yargs";
import { hideBin } from "yargs/helpers";

export const parseOptions = () => yargs(hideBin(process.argv))
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
    default: "./generated"
  })
  .option("templates-directory", {
    type: "string",
    description: "Path to the templates directory containing files with ETA syntax",
    default: "./templates"
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
  .option("npm-version", {
    type: "string",
    description: "Version of the generated npm project - required when --emit-npm-project option is set"
  })
  .parse();
