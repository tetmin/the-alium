# dAIly Mash
Generating satirical AI news using AI

## Usage Guide
Clone repo, setup Github Pages, [Modal Labs](https://modal.com/docs/guide) & then deploy with:
```
```
### Development Setup
For local testing:
```
modal run server.py
```
For local development install **poetry** for package management
```
curl -sSL https://install.python-poetry.org | python3 -
poetry install
```
and to serve the static site locally install Ruby + Jekyll & then run:
```
eval "$(rbenv init -)"
bundle exec jekyll server
```