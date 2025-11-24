import ts from "typescript";

export const compile = (code: string) => {
  const file = "file.ts";

  const host = ts.createCompilerHost({ declaration: true });
  host.readFile = () => code;
  host.fileExists = () => true;
  host.getSourceFile = (fileName, versionOrOptions) => ts.createSourceFile(fileName, code, versionOrOptions);

  const program = ts.createProgram([ file ], {
    declaration: true,
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022
  }, host);

  const output: Record<string, string> = {};
  host.writeFile = (name, text) => (output[name] = text);

  program.emit();

  return {
    js: output["file.js"],
    dts: output["file.d.ts"]
  };
};
