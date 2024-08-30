# Wax spec generator

Wax library REST API specification generator

## Running

We currently only support Swagger json files. You should download any schema file, like [`https://api.syncad.com/hafbe/`](https://api.syncad.com/hafbe/) and then specify its path to the `generate-wax-spec` binary.

See the help message using the following command:

```bash
npx generate-wax-spec --help
```

### Examples

#### generate JS and D.TS files only using the hafbe namsepace

```bash
npx generate-wax-spec -i data/hafbe.json -N hafbe
```

#### Emit entire npm project along the JS and D.TS files

```bash
npx generate-wax-spec -i data/hafbe.json -N hafbe -e --npm-name "@hiveio/wax-api-hafbe" --npm-version 1.27.0-rc1
```

## Building

```bash
pnpm install

pnpm run build
```

This shall generate JavaScript files into the `dist` directory

## License

See the license in the [LICENSE.md](LICENSE.md) file
