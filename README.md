# The Alium
An AI generated satirical newspaper.

The flow is roughly:
- Source news articles to inspire the story (Metaphor/Exa, Twitter trends, @alium_ai mentions)
- Edit articles into satirical stories (headline, text, image)
- Publish the story (Jekyll Blog on Github Pages, Twitter)

## TODO
- [x] ~~Find a better news source than [GNews API](https://gnews.io/)~~
- [x] ~~Improve image generation (article title -> image prompt is not very good & gets censored sometimes)~~
- [x] ~~Refactor codebase to extend source, editor, publisher~~
- [x] ~~Publisher: Virtual screenshot of story for posting to Twitter as an image~~
- [x] ~~Editor: Define an image style, improve image consistency & humour~~
- [x] ~~Source: Don't source articles about disasters e.g. war, murder, etc.~~
- [ ] Editor: Enable LiteLLM caching for development
- [ ] Source: Improve Twitter caching (not currently persistent on Modal, only for local development)
- [ ] Source: Make @alium_ai mentions work given Twitter rate limits
- [ ] Source: More alternative news sources e.g. https://www.brief.news/

## Usage Guide
### Local Development
For local Python development using [uv](https://docs.astral.sh/uv/):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python server.py
```
To run with [Modal](https://modal.com/), first setup secrets, then:
```
modal run server.py
```
To serve the static site locally install Ruby + Jekyll & then run:
```
eval "$(rbenv init -)"
bundle exec jekyll server
```

### To create your own site
- Clone repo
- Modify _config.yml
- Setup GitHub Pages
- Install [Modal Labs](https://modal.com/docs/guide)
- Add your own secrets to Modal
- Deploy Modal server manually or setup ci-cd as per .github/workflows/ci-cd.yml
```
modal deploy server.py
```

### To publish
Manually publish stories by running:
```
modal run server.py::generate_and_publish_stories
```
Or deploy the Modal server and let it run on the schedule:
```
modal deploy server.py
```