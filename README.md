# pepscraper

A Python program for mining PEP and PDEP repositories.

### Purpose

_pepscraper_ is designed to contribute to a dataset of enhancement proposals of OSS projects. It scrapes GitHub revisions, mailing lists and discussion fora used to maintain Python Enhancement Proposals (PEPs) and Pandas Enhancement Proposals (PDEPs) and stores the results into a database for easy access.

This program was designed as part of the CSE3000 Research Project course at the Faculty of Electrical Engineering, Mathematics and Computer Science at Delft Technical University.

### Usage

Prerequisites:
- [uv](https://docs.astral.sh/uv/)
- [git](https://git-scm.com/)
- A GitHub API token

Installation (bash):
- `git clone https://github.com/timraay/pepscraper.git`
- `export GITHUB_ACCESS_TOKEN=YOUR_API_TOKEN_HERE` (replace `YOUR_API_TOKEN_HERE`)

Running:
- `uv run main.py`

Fetched web pages and mail repositories are cached inside of the `./data` directory. Delete this directory to re-run with a clean slate.

When first installed, no cached data is available. Expect to run into rate limits and long run times (more than 2 hours).

The resulting database can be found at `./data/pepscraper.db`.
