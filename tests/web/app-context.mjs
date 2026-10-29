// Supply the shared display selector when exercising existing app handlers in isolation.
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
export function appContext(values = {}) {
  const context = vm.createContext({replay:null, ...values});
  vm.runInContext(source.slice(source.indexOf('function displayedState()'),
    source.indexOf('let state, selected')), context);
  return context;
}
