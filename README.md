# Wax spec generator

Wax library REST API specification generator

## Running

We currently only support Swagger json files. You should download any schema file, like [`https://api.syncad.com/hafbe/`](https://api.syncad.com/hafbe/) and then specify its path to the `dev` script:

```bash
pnpm install

npm run dev data/hafbe.json
```

This shall generate JavaScript and TypeScript declaration files into the `generated` directory

## Testing

After [generating](#running) you can try it on the live wax instance in the [`wax-test/wax-test.ts`](wax-test/wax-test.ts) file:

```bash
pnpx tsx wax-test/wax-test.ts
```
