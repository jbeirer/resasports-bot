#! /usr/bin/env bash

# Install dependencies into the in-project .venv
uv sync

# Install pre-commit hooks
uv run pre-commit install --install-hooks
