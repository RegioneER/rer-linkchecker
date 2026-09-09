import type { ConfigType } from '@plone/registry';
import linkSVG from '@plone/volto/icons/link.svg';

// The msgid these two strings carry is declared with defineMessages in
// LinkcheckerReport, which is where i18n extraction picks it up: no react-intl
// import here, since it is not a dependency of this package.
//
// `group` is translated by Volto, which runs it through intl.formatMessage as a
// msgid (Controlpanels.jsx:143-151), so it has to be one core already knows —
// 'Content' lands the entry in the same group as the built-in content panels.
// `title` is NOT translated: Controlpanels.jsx renders it raw, so it stays in
// english in the /controlpanel listing whatever the locale. Hardcoding italian
// here would break the other locales this addon ships.
const CONTROL_PANEL_ID = 'linkchecker';
const CONTROL_PANEL_TITLE = 'Broken links';
const CONTROL_PANEL_GROUP = 'Content';

export default function install(config: ConfigType) {
  config.settings.controlpanels = [
    ...config.settings.controlpanels,
    {
      '@id': `/${CONTROL_PANEL_ID}`,
      group: CONTROL_PANEL_GROUP,
      title: CONTROL_PANEL_TITLE,
    },
  ];
  // Keyed by the panel id, i.e. the last segment of its @id: that is what
  // Controlpanels.jsx looks the icon up by. Any other key silently falls back
  // to the default icon.
  config.settings.controlPanelsIcons = {
    ...config.settings.controlPanelsIcons,
    [CONTROL_PANEL_ID]: linkSVG,
  };
  return config;
}
