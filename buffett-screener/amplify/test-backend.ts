import { defineBackend } from '@aws-amplify/backend';
import { data } from './data/resource';

const backend = defineBackend({ data });

console.log("Tables:", Object.keys(backend.data.resources.tables || {}));
console.log("CfnResources:", Object.keys(backend.data.resources.cfnResources || {}));
if (backend.data.resources.cfnResources.amplifyDynamoDbTables) {
    console.log("Amplify tables:", Object.keys(backend.data.resources.cfnResources.amplifyDynamoDbTables));
}
