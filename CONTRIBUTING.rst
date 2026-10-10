============
Contributing
============

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

Types of Contributions
----------------------

Report Bugs
~~~~~~~~~~~

Report bugs at https://github.com/jbeirer/resasports-bot/issues

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

Fix Bugs
~~~~~~~~

Look through the GitHub issues for bugs. Anything tagged with "bug"
and "help wanted" is open to whoever wants to implement a fix for it.

Implement Features
~~~~~~~~~~~~~~~~~~

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

Write Documentation
~~~~~~~~~~~~~~~~~~~

pysportbot could always use more documentation, whether as part of
the official docs, in docstrings, or even on the web in blog posts, articles,
and such.

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file an issue at
https://github.com/jbeirer/resasports-bot/issues.

If you are proposing a new feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

Get Started!
------------

Ready to contribute? Here's how to set up `pysportbot` for local
development. Please note this documentation assumes you already have
`uv <https://docs.astral.sh/uv/>`_ and ``Git`` installed and ready to go.

| 1. Fork the `resasports-bot` repo on GitHub.

| 2. Clone your fork locally:

   .. code-block:: bash

        cd <directory_in_which_repo_should_be_created>
        git clone git@github.com:YOUR_NAME/resasports-bot.git


| 3. Now we need to install the environment. Navigate into the directory

   .. code-block:: bash

       cd resasports-bot

   Then, create the virtual environment (``.venv``) and install the pre-commit hooks with:

   .. code-block:: bash

        make install

   This runs ``uv sync`` followed by ``uv run pre-commit install``. uv will download
   a suitable Python version if needed. Run commands in the environment with
   ``uv run <command>``, or activate it with ``source .venv/bin/activate``.

| 4. Create a branch for local development:

   .. code-block:: bash

        git checkout -b name-of-your-bugfix-or-feature

   Now you can make your changes locally.


| 5. Don't forget to add test cases for your added functionality to the ``tests`` directory.

| 6. When you're done making changes, check that your changes pass the formatting tests.

   .. code-block:: bash

        make check

| 7. Now, validate that all unit tests are passing:

   .. code-block:: bash

        make test

| 8. Optionally, run the tests against a specific Python version supported by the package:

   .. code-block:: bash

        uv run --python 3.11 pytest

   The CI pipeline runs the tests on all supported Python versions, so you can also skip this
   step locally.

| 9. Commit your changes and push your branch to GitHub:

   .. code-block:: bash

        git add .
        git commit -m "Your detailed description of your changes."
        git push origin name-of-your-bugfix-or-feature

| 10. Submit a pull request through the GitHub website.

Pull Request Guidelines
---------------------------

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.

2. If the pull request adds functionality, the docs should be updated. Put your
   new functionality into a function with a docstring, and add the feature to
   the list in README.rst.
