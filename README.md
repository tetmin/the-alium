# The Alium
Generating satirical AI news using AI.

New articles are generated & posted 3 times daily on www.thealium.com & shared [@alium_ai](https://twitter.com/alium_ai):
- Get top article matching the 'artificial intelligence' filter from GNews API
- Generate satirical article based only on the title using GPT-4 (with fallback to GPT 3.5)
- Generate image prompt with GPT 3.5 & image with DALLE-2
- Create post as a markdown file

## TODO
- [x] ~~Find a better news source than [GNews API](https://gnews.io/)~~
- [ ] Improve image generation (article title -> image prompt is not very good)

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
modal deploy server.py
```
