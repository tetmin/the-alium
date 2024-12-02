import base64
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import dotenv

import cloudinary.uploader
import litellm
import modal
import numpy as np
import pytz
import requests
import tweepy
from pydantic import BaseModel, HttpUrl
from sklearn.metrics.pairwise import cosine_similarity
from together import Together

dotenv.load_dotenv()
litellm.success_callback = ["athina"]  # For monitoring

# Initialize Modal Labs app for serverless deployment
image = modal.Image.debian_slim().poetry_install_from_file("pyproject.toml")
app = modal.App(
    name="the-alium",
    image=image,
    secrets=[modal.Secret.from_name("alium-secrets")],
    mounts=[modal.Mount.from_local_dir("prompts", remote_path="/root/prompts")],
)


# Handles GitHub repository operations (posting story markdown files and checking existing content)
class JekyllPublisher:
    def __init__(self):
        self.owner = "tetmin"
        self.repo = "the-alium"
        self.token = os.environ["GITHUB_TOKEN"]
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def publish(self, story):
        jekyll_content = self.file_content(story)
        story.blog_url = self._create_filename(story)
        return self.commit_new_blog_post(story.blog_url, jekyll_content)

    def commit_new_blog_post(self, filename, content):
        path = f"_posts/{filename}"
        data = {
            "message": "Create a new post",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main",
        }
        response = requests.put(
            f"{self.base_url}/{path}",
            headers=self.headers,
            data=json.dumps(data),
            timeout=10,
        )
        return response

    def file_content(self, story):
        story.title = story.title.replace('"', "'")
        story.image_prompt = story.image_prompt.replace('"', "'")
        return (
            f'---\ntitle: "{story.title}"\ndate: {self._get_datetime_for_frontmatter()}\nimage: {story.image_url}\nllm: {story.llm}\n---\n'
            f'![Alt Text]({story.image_url} "{story.image_prompt}")\n\n{story.content}'
            f"\n\n---\n*AInspired by: [{story.original_article.title}]({story.original_article.url})*"  # modified
        )

    def get_existing_article_titles(self):
        response = requests.get(f"{self.base_url}/_posts", timeout=10)
        if response.status_code == 200:
            data = json.loads(response.text)
            return [file["name"] for file in data]
        return []

    def get_recent_article_titles(self, months_ago=3):
        all_titles = self.get_existing_article_titles()
        cutoff_date = datetime.now() - timedelta(days=months_ago * 30)
        filtered_titles = []
        for title_with_date in all_titles:
            try:
                # Extract date and title using regex for robustness
                match = re.match(r"(\d{4}-\d{2}-\d{2})-(.*).md", title_with_date)

                if match:
                    date_str = match.group(1)
                    date = datetime.strptime(date_str, "%Y-%m-%d")

                    if date >= cutoff_date:
                        title = match.group(2)
                        filtered_titles.append(title)
            except ValueError:
                print(f"Invalid date format in filename: {title_with_date}")
                continue
        return filtered_titles

    def _get_datetime_for_frontmatter(self):
        now = datetime.now(pytz.utc).astimezone(pytz.timezone("Europe/London"))
        return now.strftime("%Y-%m-%d %H:%M:%S %z")

    def _get_date_for_filename(self):
        now = datetime.now(pytz.utc).astimezone(pytz.timezone("Europe/London"))
        return now.strftime("%Y-%m-%d")

    def _clean_filename(self, filename):
        cleaned = re.sub(r'[\\/:"\'\’\‘*?<>|]', "", filename)
        cleaned = cleaned.replace(" ", "_").lower()
        return cleaned[:255]

    def _create_filename(self, story):
        return f"{self._get_date_for_filename()}-{self._clean_filename(story.original_article.title)}.md"


# Manages Twitter API interactions for posting stories
class TwitterPublisher:
    def __init__(self):
        self.client = tweepy.Client(
            consumer_key=os.environ["TWITTER_API_KEY"],
            consumer_secret=os.environ["TWITTER_API_SECRET"],
            access_token=os.environ["TWITTER_ACCESS_TOKEN"],
            access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        auth = tweepy.OAuthHandler(os.environ["TWITTER_API_KEY"], os.environ["TWITTER_API_SECRET"])
        auth.set_access_token(
            os.environ["TWITTER_ACCESS_TOKEN"],
            os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        self.api = tweepy.API(auth)

    def upload_media(self, image_url):
        response = requests.get(image_url, timeout=10)
        with open("temp.png", "wb") as out_file:
            out_file.write(response.content)
        response = self.api.media_upload("temp.png")
        return response.media_id_string

    def publish(self, story):
        media_id = self.upload_media(story.image_url)
        post_url = story.blog_url[:-3].replace("-", "/")
        post_url = f"https://www.thealium.com/{post_url}.html"
        text = f"{story.title}\n\n{post_url}?nolongurl"
        return self.client.create_tweet(text=text, media_ids=[media_id] if media_id else None)


# Handles publishing stories across multiple platforms, currently via GitHub Pages (for Jekyll) and Twitter
class MultiPublisher:
    def __init__(self):
        self.publishers = [JekyllPublisher(), TwitterPublisher()]

    def publish_story(self, story):
        return [publisher.publish(story) for publisher in self.publishers]

    @property
    def golden_source(self) -> JekyllPublisher:
        return next(p for p in self.publishers if isinstance(p, JekyllPublisher))


# Sources articles from news sources (currently only Metaphor implemented)
class NewsSource:
    """
    Fetches recent AI news articles from Metaphor API. Implements get_articles and returns a list of Article instances.
    """

    def __init__(self, search_query):
        self.query = search_query
        self.api_key = os.environ["METAPHOR_API_KEY"]
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": self.api_key,
        }

    def get_articles(self, n_articles):
        url = "https://api.metaphor.systems/search"
        payload = {
            "query": f"If you're interested in news about innovations in {self.query} by people or companies, you need to check out this article:",
            "numResults": 100,
            "startPublishedDate": (datetime.today() - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z"),
        }
        response = requests.post(url, json=payload, headers=self.headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            raw_articles = data.get("articles", data.get("results", []))
            articles = [Article.from_metaphor(article_data) for article_data in raw_articles][:n_articles]
            return articles
        return []

    def get_novel_articles(self, n_articles, existing_titles, similarity_threshold=0.9):
        articles = self.get_articles(n_articles * 10)
        article_titles = [article.title for article in articles if article.title]

        if not article_titles or not existing_titles:
            return articles[:n_articles]

        all_titles = article_titles + existing_titles
        embeddings = Article.get_embeddings(all_titles)
        article_embeddings, existing_embeddings = (
            np.array(embeddings[: len(article_titles)]),
            np.array(embeddings[len(article_titles) :]),
        )

        similarities = cosine_similarity(article_embeddings, existing_embeddings)
        max_similarities = np.max(similarities, axis=1)

        sorted_indices = np.argsort(max_similarities)  # ascending order (least similar first)
        novel_articles = [articles[i] for i in sorted_indices if max_similarities[i] <= similarity_threshold][
            :n_articles
        ]
        return novel_articles


# Data structure for holding articles sourced from news sources
class Article(BaseModel):
    title: str
    url: HttpUrl
    data: dict

    @classmethod
    def from_metaphor(cls, article_data):
        return cls(
            title=article_data.get("title", ""),
            url=article_data.get("url", ""),
            data=article_data,
        )

    @staticmethod
    def get_embeddings(texts):
        """Utility function to batch embed input texts for similarity comparisons"""
        response = litellm.embedding(model="text-embedding-ada-002", input=texts)
        return [item["embedding"] for item in response.data]


# Data structure for holding & displaying generated satirical story content
class Story(BaseModel):
    original_article: Article
    title: str
    content: str
    image_prompt: str = ""
    blog_url: HttpUrl = ""
    image_url: HttpUrl = ""
    llm: str = ""

    def __str__(self) -> str:
        return f"""
------------
Title: {self.title}
Image prompt: {self.image_prompt}
Image URL: {self.image_url}
------------
{self.content}
------------
Source: {self.original_article.title}
URL: {self.original_article.url}"""


# Edits articles into stories
class StoryEditor:
    def __init__(self):
        pass

    def generate_story(self, article, model="gpt-4o-mini", image_quality="standard", metadata=None, editor=False):
        # Check for article title moderation issues & write a story
        if self._get_moderation_flag(article.title):
            print(f"Moderation issue with the LLM proposed story title: {article.title}")
            return None

        STORY_PROMPT = self.load_prompt(
            "story",
            news_headline_to_write_satirical_version_of=article.title,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )
        messages = [
            {"role": "user", "content": STORY_PROMPT},
            {"role": "assistant", "content": "<satire_development>"},  # assistant prefill
        ]
        response = litellm.completion(model=model, messages=messages, temperature=0.8, metadata=metadata)
        title = self.extract_between_tags("article_headline", response.choices[0].message.content, strip=True)[0]
        content = self.extract_between_tags("article", response.choices[0].message.content, strip=True)[0]
        story = Story(original_article=article, title=title, content=content, llm=model)

        if editor:
            # Reflect & edit the story
            EDITOR_PROMPT = self.load_prompt("editor", original_article_headline=title, original_article=content)
            messages = [
                {"role": "user", "content": EDITOR_PROMPT},
                {"role": "assistant", "content": "<satire_review>"},  # assistant prefill
            ]
            response = litellm.completion(model=model, messages=messages, temperature=0.5, metadata=metadata)
            title = self.extract_between_tags("article_headline", response.choices[0].message.content, strip=True)[0]
            content = self.extract_between_tags("article", response.choices[0].message.content, strip=True)[0]
            story = Story(original_article=article, title=title, content=content, llm=model)

        # Write the image prompt & check for moderation issues
        IMAGE_PROMPT = self.load_prompt("image")
        messages = [
            {"role": "system", "content": IMAGE_PROMPT},
            {"role": "user", "content": f"News Headline: {story.title}"},
            {"role": "assistant", "content": "Image Idea:"},
        ]
        response = litellm.completion(model="gpt-4o-mini", messages=messages, temperature=0.8, metadata=metadata)
        image_prompt = response.choices[0].message.content
        if self._get_moderation_flag(image_prompt):
            print(f"Image prompt failed moderation: {image_prompt}")
            return None
        story.image_prompt = image_prompt

        # Generate the image
        image_provider = "together"  # Temporary since it's free for a while
        if image_provider == "together":
            together_client = Together(api_key=os.environ["TOGETHER_API_KEY"])
            response = together_client.images.generate(
                prompt=image_prompt,
                model="black-forest-labs/FLUX.1-schnell-Free",
                width=1024,
                height=768,
                steps=4,
                n=1,
                response_format="b64_json",
            )
            # Convert base64 to URL by uploading to Cloudinary
            image_data = base64.b64decode(response.data[0].b64_json)
            story.image_url = cloudinary.uploader.upload(image_data)["secure_url"]
        else:
            response = litellm.image_generation(
                prompt=image_prompt,
                model="dall-e-3",
                n=1,
                size="1024x1024",
                quality=image_quality,
                metadata=metadata,
            )
            story.image_url = cloudinary.uploader.upload(response.data[0].url)["secure_url"]
        return story

    @staticmethod
    def load_prompt(file_name: str, **kwargs) -> str:
        """Load a single markdown prompt from a file and replace placeholders with provided values."""
        template = Path(f"prompts/{file_name}.assistant.md").read_text()
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            template = template.replace(placeholder, str(value))
        return template

    @staticmethod
    def extract_between_tags(tag: str, string: str, strip: bool = False) -> list[str]:
        ext_list = re.findall(f"<{tag}>(.+?)</{tag}>", string, re.DOTALL)
        if strip:
            ext_list = [e.strip() for e in ext_list]
        return ext_list

    @staticmethod
    def _parse_story_completion_markdown(response):
        lines = response.split("\n", 1)
        title = re.sub(r"^#+\s*|\*\*|\*\s*", "", lines[0])
        content = lines[1] if len(lines) > 1 else ""
        return title, content

    @staticmethod
    def _get_moderation_flag(prompt):
        response = litellm.moderation(input=prompt, model="text-moderation-latest")
        return response.results[0].flagged


# Specify the query filter for source articles (e.g., "artificial intelligence")
source = NewsSource("artificial intelligence")
editor = StoryEditor()
publisher = MultiPublisher()


# Main function to generate and publish satirical stories
def _generate_and_publish_stories(test_mode: bool = False):
    # Set up logging & cheaper test mode models
    print("Running in test mode" if test_mode else "Running in production mode")
    model = (
        "claude-3-5-haiku-20241022" if test_mode else "claude-3-5-sonnet-20241022"
    )  # Use smaller model in test mode anthropic/claude-3-5-sonnet-latest | claude-3-5-sonnet-20241022 | claude-3-5-haiku-20241022
    image_quality = "standard" if test_mode else "hd"
    litellm.set_verbose = True if test_mode else False  # For debugging
    metadata = {
        "environment": "development" if test_mode else "production",
        "session_id": os.environ["MODAL_TASK_ID"] if not modal.is_local() else uuid.uuid4(),
    }

    # Fetch titles of the articles recently edited into stories
    print("Getting existing titles from past 3 months...")
    existing_titles = publisher.golden_source.get_recent_article_titles(months_ago=3)

    # Fetch and filter new news articles based on similarity to existing articles
    print(f"Fetching novel articles about '{source.query}'...")
    similarity_threshold = 0.95 if test_mode else 0.9  # Higher threshold in test mode
    articles = source.get_novel_articles(1, existing_titles, similarity_threshold)
    print(f"Found {len(articles)} novel articles")

    # Edit each article into a satirical story
    for i, article in enumerate(articles, 1):
        print(f"Generating satirical story {i} of {len(articles)}...")
        story = editor.generate_story(article, model, image_quality, metadata, editor=False)
        print(story)

        # Publish if not in test mode and story generation succeeded
        if story and not test_mode:
            print("Publishing story...")
            publisher.publish_story(story)


# To test fully locally (no modal - requires .env file): poetry run python server.py
# To test in a remote modal container: modal run server.py
# To publish stories manually: modal run server.py::generate_and_publish_stories
# To deploy on the schedule: modal deploy server.py
@app.function(schedule=modal.Cron("1 14 * * *"))
def generate_and_publish_stories(test_mode: bool = False):
    _generate_and_publish_stories(test_mode)


@app.local_entrypoint()
def main():
    generate_and_publish_stories.remote(test_mode=True)


if __name__ == "__main__":
    _generate_and_publish_stories(test_mode=True)
