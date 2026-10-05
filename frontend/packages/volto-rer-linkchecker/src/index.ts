import type { ConfigType } from '@plone/registry';

import { getLinkcheckerReport } from './actions/linkchecker';
import linkcheckerReducer from './reducers/linkchecker';
import LinkcheckerReport from './components/LinkcheckerReport/LinkcheckerReport';
import ToolbarUserMenu from './components/manage/toolbar/ToolbarUserMenu';

function applyConfig(config: ConfigType) {
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
  config.settings.appExtras = [
    ...config.settings.appExtras,
    {
      match: '',
      component: ToolbarUserMenu,
      props: {},
    },
  ];

  return config;
}

export default applyConfig;
export { getLinkcheckerReport };
