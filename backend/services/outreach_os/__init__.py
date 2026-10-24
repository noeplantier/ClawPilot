"""OutreachOS discovery → signals → score → draft pipeline.

Everything here except `pipeline.py` is pure: no database, no network, no clock (callers inject
`now`). Sources and analyzers are `Protocol`s so tests and the dry-run mode use local fixtures.
"""
