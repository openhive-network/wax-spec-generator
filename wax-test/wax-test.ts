import WaxExtendedData from "../generated/out.js";
import { createHiveChain } from "@hiveio/wax";

const chain = (await createHiveChain()).extendRest(WaxExtendedData);

chain.restApi // Test your generated data here
