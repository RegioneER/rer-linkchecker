import React from 'react';
import { useSelector } from 'react-redux';
import { Link } from 'react-router-dom';

import { Icon } from '@plone/volto/components';
import rightArrowSVG from '@plone/volto/icons/right-key.svg';
import { Plug } from '@plone/volto/components/manage/Pluggable';

export const ToolbarUserMenu = () => {
  const linkcheckerAction = useSelector((state) =>
    (state.actions?.actions?.user ?? []).find(
      (action) => action.id === 'rer-linkchecker',
    ),
  );
  return linkcheckerAction ? (
    <Plug pluggable="toolbar-user-menu" id="rer-linkchecker-toolbar">
      <li>
        <Link
          to="/controlpanel/linkchecker"
          tabIndex={0}
          className="deleteBlocks"
          id="toolbar-customer-satisfaction-panel"
        >
          {linkcheckerAction.title} <Icon name={rightArrowSVG} size="24px" />
        </Link>
      </li>
    </Plug>
  ) : null;
};

export default ToolbarUserMenu;
