// gravit-ui/js/reducers/index.js
import { reducers as messages } from './messages.js';
import { reducers as discover } from './discover.js';
import { reducers as account } from './account.js';

export const reducers = { ...messages, ...discover, ...account };
