import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { schemas } from '../types/schemas';
import type { Design, EditOp } from '../types';

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
for (const schema of schemas) ajv.addSchema(schema);

function assertShape(name: string, value: unknown): void {
  const validate = ajv.getSchema(`https://brand-copilot.local/schema/${name}.schema.json`)!;
  if (!validate(value)) throw new Error(`Invalid ${name}: ${ajv.errorsText(validate.errors)}`);
}
export function validateDesign(value: unknown): asserts value is Design { assertShape('Design', value); }
export function validateEditOp(value: unknown): asserts value is EditOp { assertShape('EditOp', value); }
