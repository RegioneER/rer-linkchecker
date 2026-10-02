import type { ConfigType } from '@plone/registry';
import linkSVG from '@plone/volto/icons/link.svg';

// `group` is translated by Volto as a msgid (Controlpanels.jsx:143-151), so it
// has to be one core already knows: 'Content' lands the entry among the
// built-in content panels. `title` is NOT translated — rendered raw — so it
// stays in english in the listing whatever the locale, and cannot follow the
// title of the panel's own page.
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
