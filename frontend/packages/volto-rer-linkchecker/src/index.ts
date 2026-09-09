import type { ConfigType } from '@plone/registry';
import installSettings from './config/settings';

import { getLinkcheckerReport } from './actions/linkchecker';
import linkcheckerReducer from './reducers/linkchecker';
import LinkcheckerReport from './components/LinkcheckerReport/LinkcheckerReport';

function applyConfig(config: ConfigType) {
  installSettings(config);

  config.addonReducers = {
    ...config.addonReducers,
    linkchecker: linkcheckerReducer,
  };

  config.addonRoutes = [
    ...(config.addonRoutes || []),
    {
      path: '/controlpanel/linkchecker',
      component: LinkcheckerReport,
    },
  ];

  return config;
}

export default applyConfig;
export { getLinkcheckerReport };
