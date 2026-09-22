"""Hypothesis profiles for the property suite.

Both runners import this package before any test module, so the profile
loads here. The `HYPOTHESIS_PROFILE` environment variable names the
profile to load. The default is `dev`. The `HYPOTHESIS_EXAMPLES`
environment variable replaces the example count of that profile and
keeps its other settings.
"""

from os import environ

from hypothesis import settings

EXAMPLES_ENV_VAR = 'HYPOTHESIS_EXAMPLES'

# Fast feedback for the local edit loop.
settings.register_profile('dev', max_examples=100)
# Deeper search; print_blob replaces the example database CI does not keep.
settings.register_profile('ci', max_examples=1000, print_blob=True)

profile = environ.get('HYPOTHESIS_PROFILE', 'dev')
if EXAMPLES_ENV_VAR in environ:
    settings.register_profile(
        'manual',
        parent=settings.get_profile(profile),
        max_examples=int(environ[EXAMPLES_ENV_VAR]),
    )
    profile = 'manual'
settings.load_profile(profile)
