import os


# the .mo files are not versioned: have zope.i18n build them from the .po
# when the layers register the translations, or the tests read stale catalogs
os.environ.setdefault("zope_i18n_compile_mo_files", "true")

from pytest_plone import fixtures_factory
from rer.linkchecker.testing import ACCEPTANCE_TESTING
from rer.linkchecker.testing import FUNCTIONAL_TESTING
from rer.linkchecker.testing import INTEGRATION_TESTING


pytest_plugins = ["pytest_plone"]


globals().update(
    fixtures_factory((
        (ACCEPTANCE_TESTING, "acceptance"),
        (FUNCTIONAL_TESTING, "functional"),
        (INTEGRATION_TESTING, "integration"),
    ))
)
