"""Cross-cutting tests that belong to no single app.

`core` holds these because they assert things that span apps: the served URL
surface, the shape of every response body, and the query cost of the
read-heavy endpoints. They were four `test_*.py` files sitting directly in
`apps/core/`, where they made up more than a third of the package and buried
the handful of modules that are actually shared infrastructure.

`base.py` is not a test module -- it holds the `ThrottledAPITestCase` other
apps subclass. It is deliberately named so the `test*.py` discovery pattern
does not pick it up.
"""
