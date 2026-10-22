import google.adk

import aurora


def test_package_imports_with_pinned_adk():
    assert aurora.__doc__
    assert google.adk.__version__ == "2.12.0"
