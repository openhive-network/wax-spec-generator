import fs from "node:fs";

export const parseNamespace = (swaggerFilePath: string): string | undefined => {
  const content = fs.readFileSync(swaggerFilePath, "utf-8");

  try {
    const jsonContent = JSON.parse(content);

    return jsonContent.servers[0].url.split("/").pop();
  }catch {
    return undefined;
  }
};
