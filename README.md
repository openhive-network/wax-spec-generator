# Wax spec generator

Wax library REST/JSON-RPC API specification generator

No-download example usage:

```bash
pnpm dlx @hiveio/wax-spec-generator generate-wax-spec -i data.json
```

## Install

This is a [Node.js](https://nodejs.org/en/) module available through the
[npm registry](https://www.npmjs.com/):

```bash
pnpm add @hiveio/wax-spec-generator
```

Before installing, [download and install Node.js](https://nodejs.org/en/download/).
Node.js 18 or higher is required.

Installation is done using the
[`npm install` command](https://docs.npmjs.com/getting-started/installing-npm-packages-locally):

If you want to use **development** versions of our packages, set `@hiveio` scope to use our GitLab registry:

```bash
echo @hiveio:registry=https://gitlab.syncad.com/api/v4/groups/136/-/packages/npm/ >> .npmrc
npm install @hiveio/wax-spec-generator
```

## Running

We currently only support Swagger json files. You should download any schema file, like [`https://api.syncad.com/hafbe/`](https://api.syncad.com/hafbe/) and then specify its path to the `generate-wax-spec` binary.

See the help message using the following command:

```bash
npx generate-wax-spec --help
```

### Examples

#### generate JS and D.TS files only using the hafbe namsepace

```bash
npx generate-wax-spec -i data/hafbe.json -N hafbe -T rest
```

#### Emit entire npm project along the JS and D.TS files

```bash
npx generate-wax-spec -i data/hafbe.json -N hafbe -T rest -e --npm-name "@hiveio/wax-api-hafbe" --npm-version 1.27.0-rc1
```

## Building

```bash
pnpm install

pnpm run build
```

This shall generate JavaScript files into the `dist` directory

## License

See the license in the [LICENSE.md](LICENSE.md) file
