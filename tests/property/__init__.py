"""Hypothesis profiles for the property suite.

Both runners import this package before any test module, so the profile
loads here. The `HYPOTHESIS_PROFILE` environment variable names the
profile to load. The default is `dev`.
"""

from os import environ

from hypothesis import settings

# Fast feedback for the local edit loop.
settings.register_profile('dev', max_examples=100)
# Deeper search; print_blob replaces the example database CI does not keep.
settings.register_profile('ci', max_examples=1000, print_blob=True)

settings.load_profile(environ.get('HYPOTHESIS_PROFILE', 'dev'))
