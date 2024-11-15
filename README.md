# The Alium
Generating satirical AI news using AI.

New articles are generated & posted daily on www.thealium.com & shared [@alium_ai](https://twitter.com/alium_ai):
- Get top article matching the 'artificial intelligence' filter from GNews API or Metaphor
- Generate satirical article based only on the title using LLM
- Generate image prompt with LLM & image with DALLE-2
- Create post as a markdown file

## TODO
- [x] ~~Find a better news source than [GNews API](https://gnews.io/)~~
- [x] ~~Improve image generation (article title -> image prompt is not very good & gets cencored sometimes)~~

## Usage Guide
### Development Setup
For local testing you need [Modal](https://modal.com/) with secrets setup, then:
```
modal run server.py
```
For local Python development:
```
curl -sSL https://install.python-poetry.org | python3 -
poetry install
poetry run modal run server.py:test
```
To serve the static site locally install Ruby + Jekyll & then run:
```
eval "$(rbenv init -)"
bundle exec jekyll server
```
server.py will redeploy when merged to main
### To create your own site
- Clone repo
- Modify _config.yml
- Setup Github Pages
- Install [Modal Labs](https://modal.com/docs/guide)
- Add your own secrets to Modal
- Deploy Modal server manually or setup ci-cd as per .github/workflows/ci-cd.yml
```
poetry runm odal deploy server.py
```
