import path from 'node:path';
import { generate } from './generator.js';

let inputFile = process.argv[2];
if (inputFile === undefined)
  throw new Error('Missing filepath argument');
inputFile = path.isAbsolute(inputFile) ? inputFile : path.resolve(process.cwd(), inputFile);

const outputDirectory = path.resolve(process.cwd(), "generated");

generate({
  inputFile,
  outputDirectory,
  namespace: 'hafbe'
}).catch(error => {
  console.error(error);

  process.exitCode = 1;
});