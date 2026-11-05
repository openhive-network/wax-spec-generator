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

Dependency versions shared across Hive apps (TypeScript, husky) come from the pnpm catalogs of [common-ci-configuration](https://gitlab.syncad.com/hive/common-ci-configuration), which `pnpm-workspace.yaml` links to through the `npm-common-config` submodule, so check it out first:

```bash
git submodule update --init --remote npm-common-config

pnpm install

pnpm run build
```

This shall generate JavaScript files into the `dist` directory

## Python API clients

`python/` holds the Python generator (`hiveio-api-client-generator`) and `python-api-client/` the runtime package of
generated clients (`hiveio-api-client`, see its [README](python-api-client/README.md)). Apps build their Python client
package with the CI template [`templates/python_api_package.gitlab-ci.yml`](templates/python_api_package.gitlab-ci.yml)
(usage in its header) - no pyproject or lockfile of the client in the app.

## License

See the license in the [LICENSE.md](LICENSE.md) file
