# Installation

Install Python 3.12+, create a virtual environment, then install the package with `python -m pip install -e ".[dev,ingest]"`. Run `paperrule init --workspace <private-directory>` and `paperrule app`. The service binds to `127.0.0.1` only. Optional PDF and DOCX parsers are installed through the `ingest` extra.
