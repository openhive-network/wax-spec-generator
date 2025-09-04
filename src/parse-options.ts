import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const parseOptions = () => yargs(hideBin(process.argv))
  .option("add-namespace", {
    alias: "N",
    type: "string",
    description: "Namespace name for the application - adds a nested level of object with given namespace name for all of the parsed API definitions."
      + " Sets the namespace to the server URL if implicitly set (--add-namespace). Usually, when dealing with JSON-RPC APIs, the namespace would be "
      + "left empty, as the methods are globally available. For REST APIs, it's recommended to set the namespace to avoid potential name clashes. "
      + "In most cases, the namespace can be automatically deduced from the input file name, so you can just use --add-namespace without a value.",
    implies: ""
  })
  .option("api-type", {
    alias: "T",
    type: "string",
    description: "API type for the application - specifies the type of API being defined. Affects the way the definitions are generated.",
    choices: [ "jsonrpc", "rest" ],
    default: "rest"
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
    default: resolve(__dirname, "../templates")
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
