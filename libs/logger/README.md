# TLGP Logger Library

A shared structured logging utility providing consistent log formatting and global error capturing across all `tlgp-tools` applications and services.

## Overview

The logger package uses `structlog` to standardize logs in both development and production. It intercepts standard library logs, handles formatting (colored developer logs or structured JSON), and redirects output to `sys.stderr` to prevent protocol/data stream corruption (e.g. over JSON-RPC stdio transports like MCP).

## Key Features

- **`setup_logging(log_level, json_format)`**: Initializes logging handlers and formatters.
  - Development mode (`json_format=False`): Outputs highly readable, color-coded console logs.
  - Production mode (`json_format=True`): Outputs standard structured JSON.
  - Standard error redirect: Configures `StreamHandler` to route all output to `sys.stderr`.
- **`get_logger(name)`**: Retrieves a pre-configured structured logger instance.
- **`setup_excepthook()`**: Configures a global exception hook (`sys.excepthook`) to capture and log any unhandled system exceptions automatically before terminating.

## Usage

```python
from tlgp_logger import setup_logging, get_logger, setup_excepthook

# 1. Initialize logging
setup_logging(log_level="DEBUG")
setup_excepthook()

# 2. Retrieve logger and emit structured events
logger = get_logger("my_service")
logger.info("Service started", port=8000, environment="dev")
```

## Installation & Development

This package is installed and managed automatically as a workspace member within the monorepo.

To run tests:
```bash
uv run pytest
```
