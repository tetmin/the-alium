import base64
import functools
import json
import os
import pickle
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import cloudinary.uploader
import dotenv
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
    mounts=[
        modal.Mount.from_local_dir("prompts", remote_path="/root/prompts"),
        modal.Mount.from_local_dir(".cache", remote_path="/root/.cache"),
    ],
)

# Global config
METAPHOR_QUERY = "artificial intelligence"


def cache_responses(cache_file):
    """Decorator to cache API responses in test mode"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, "_test_mode") or not self._test_mode:
                return func(self, *args, **kwargs)

            cache_path = Path(cache_file)
            # Load cache
            if cache_path.exists():
                try:
                    with cache_path.open("rb") as f:
                        cache = pickle.load(f)
                        if datetime.now() - cache["timestamp"] < timedelta(days=365):
                            return cache["data"]
                except Exception as e:
                    print(f"Cache read error: {e}")
                    cache = {"timestamp": datetime.now(), "data": []}

            # Get fresh data
            data = func(self, *args, **kwargs)

            # Save to cache
            try:
                cache_path.parent.mkdir(exist_ok=True)
                with cache_path.open("wb") as f:
                    pickle.dump({"timestamp": datetime.now(), "data": data}, f)
            except Exception as e:
                print(f"Cache write error: {e}")

            return data

        return wrapper

    return decorator


class Article(BaseModel):
    """Holds an article sourced from a news source"""

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


class Story(BaseModel):
    """Holds a satirical story"""

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


class JekyllPublisher:
    """Handles GitHub repository operations (posting story markdown files and checking existing content)"""

    def __init__(self):
        self.owner = "tetmin"
        self.repo = "the-alium"
        self.token = os.environ["GITHUB_TOKEN"]
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def publish(self, story: Story):
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

    def file_content(self, story: Story):
        story.title = story.title.replace('"', "'")
        story.image_prompt = story.image_prompt.replace('"', "'")
        return (
            f'---\ntitle: "{story.title}"\ndate: {self._get_datetime_for_frontmatter()}\nimage: {story.image_url}\nllm: {story.llm}\n---\n'
            f'![Alt Text]({story.image_url} "{story.image_prompt}")\n\n{story.content}'
            f"\n\n---\n*AInspired by: [{story.original_article.title}]({story.original_article.url})*"
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

    def _create_filename(self, story: Story):
        return f"{self._get_date_for_filename()}-{self._clean_filename(story.original_article.title)}.md"


class TwitterPublisher:
    """Manages Twitter API interactions for posting stories"""

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

    def publish(self, story: Story):
        # Always post to main account first
        media_id = self.upload_media(story.image_url)
        post_url = story.blog_url[:-3].replace("-", "/")
        post_url = f"https://www.thealium.com/{post_url}.html"
        text = f"{story.title}\n\n{post_url}?nolongurl"
        response = self.client.create_tweet(text=text, media_ids=[media_id] if media_id else None)

        # If story was sourced from Twitter, reply to original thread with our tweet
        if story.original_article.data.get("source") == "twitter_mention":
            tweet_id = story.original_article.data.get("tweet_id")
            if tweet_id:
                self.client.create_tweet(
                    text="Here's your AI-generated satirical story!",
                    in_reply_to_tweet_id=tweet_id,
                    quote_tweet_id=response.data["id"],
                )

        return response


class MultiPublisher:
    """Handles publishing stories across multiple platforms"""

    def __init__(self):
        self.publishers = [JekyllPublisher(), TwitterPublisher()]

    def publish_story(self, story: Story):
        return [publisher.publish(story) for publisher in self.publishers]

    @property
    def golden_source(self) -> JekyllPublisher:
        return next(p for p in self.publishers if isinstance(p, JekyllPublisher))


class NewsSource:
    """Base class for news sources. Implements get_articles and returns a list of Article instances."""

    def get_articles(self, n_articles) -> list[Article | None]:
        raise NotImplementedError

    def get_novel_articles(self, n_articles, existing_titles, similarity_threshold=0.9) -> list[Article | None]:
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


class MetaphorSource(NewsSource):
    def __init__(self, query, test_mode: bool = False):
        self._test_mode = test_mode
        self.query = query
        self.api_key = os.environ["METAPHOR_API_KEY"]
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": self.api_key,
        }

    @cache_responses(".cache/metaphor.pkl")
    def get_articles(self, n_articles) -> list[Article | None]:
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


class TwitterTrendsSource(NewsSource):
    """Sources articles from personalised trends of an X Premium user"""

    def __init__(self, min_posts: int = 10000, test_mode: bool = False):
        self._test_mode = test_mode
        self.min_posts = min_posts
        self.client = tweepy.Client(
            consumer_key=os.environ["TWITTER_API_KEY"],
            consumer_secret=os.environ["TWITTER_API_SECRET"],
            access_token=os.environ["X_PREMIUM_ACCESS_TOKEN"],
            access_token_secret=os.environ["X_PREMIUM_ACCESS_TOKEN_SECRET"],
        )

    def _parse_post_count(self, count_str: str) -> float:
        """Convert strings like '32K' or '1.9B' to numbers"""
        multipliers = {"K": 1000, "M": 1000000, "B": 1000000000}
        count_str = count_str.strip().upper()

        if count_str[-1] in multipliers:
            number = float(count_str[:-1])
            return number * multipliers[count_str[-1]]
        return float(count_str)

    @cache_responses(".cache/twitter_trends.pkl")
    def get_articles(self, n_articles) -> list[Article | None]:
        response = self.client._make_request("GET", "/2/users/personalized_trends", user_auth=True)

        if not response.data:
            return []

        # Check for non-premium response pattern
        if len(response.data) == 1 and response.data[0].get("post_count") == "Unknown":
            print("Warning: Non-premium Twitter response received")
            return []

        # Parse and sort trends by post_count
        articles = []
        for trend in response.data:
            post_count = self._parse_post_count(trend["post_count"])
            if post_count >= self.min_posts:  # Filter out low-engagement trends
                articles.append(
                    (
                        post_count,
                        Article(
                            title=trend["trend_name"],
                            url=f"https://twitter.com/search?q={trend['trend_name']}",
                            data={
                                "post_count": post_count,
                                "category": trend.get("category"),
                                "source": "twitter_trend",
                            },
                        ),
                    )
                )

        # Sort by post_count and return just the Article objects
        return [article for _, article in sorted(articles, reverse=True)][:n_articles]


class TwitterMentionsSource(NewsSource):
    """Sources articles from Twitter mentions of the bot - uses too many monthly tweet requests"""

    def __init__(self, test_mode: bool = False):
        self._test_mode = test_mode
        # Once get it working, use the bearer token here instead of OAuth
        self.client = None

    @cache_responses(".cache/twitter_mentions.pkl")
    def get_articles(self, n_articles) -> list[Article | None]:
        # Get mentions since last check
        mentions = self.client.get_users_mentions(
            1663646123674812418,
            max_results=100,
            expansions=["referenced_tweets.id"],
            tweet_fields=["created_at", "text", "author_id", "conversation_id", "referenced_tweets"],
        )

        articles = []
        # Convert mentions to Article objects
        for tweet in mentions["data"] or []:
            parent_tweet = (
                next((ref for ref in mentions.includes["tweets"] if ref.id == tweet.conversation_id), None)
                if mentions.includes and "tweets" in mentions.includes
                else None
            )

            title = parent_tweet.text if parent_tweet else tweet.text
            articles.append(
                Article(
                    title=title,
                    url=f"https://twitter.com/user/status/{tweet.conversation_id or tweet.id}",
                    data={
                        "tweet_id": tweet.id,
                        "conversation_id": tweet.conversation_id,
                        "author_id": tweet.author_id,
                        "source": "twitter_mention",
                    },
                )
            )

        return articles[:n_articles]


class StoryEditor:
    """Edits articles into stories"""

    def __init__(self):
        pass

    def generate_story(
        self, article: Article, model="gpt-4o-mini", image_quality="standard", metadata=None, editor=False
    ) -> Story | None:
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


# Main function to generate and publish satirical stories
def _generate_and_publish_stories(test_mode: bool = False):
    # Set up logging & cheaper test mode models
    print("Running in test mode" if test_mode else "Running in production mode")
    model = (
        "claude-3-5-haiku-20241022" if test_mode else "claude-3-5-sonnet-20241022"
    )  # Use smaller model in test mode
    image_quality = "standard" if test_mode else "hd"
    similarity_threshold = 0.95 if test_mode else 0.9  # Higher threshold in test mode
    litellm.set_verbose = True if test_mode else False  # For debugging
    metadata = {
        "environment": "development" if test_mode else "production",
        "session_id": os.environ["MODAL_TASK_ID"] if not modal.is_local() else uuid.uuid4(),
    }

    # Fetch titles of the articles recently edited into stories
    print("Getting existing titles from past 3 months...")
    publisher = MultiPublisher()
    existing_titles = publisher.golden_source.get_recent_article_titles(months_ago=3)

    # Source articles to base stories on
    articles = []
    # First check Twitter mentions
    # TODO: Enable once figure out how to do within free tier
    # print("Checking for Twitter mentions...")
    # mentions_source = TwitterMentionsSource(test_mode=test_mode)
    # articles = mentions_source.get_novel_articles(1, existing_titles, similarity_threshold)

    # If no Twitter mentions, check Twitter trends
    if not articles:
        print("Checking Twitter trends...")
        trends_source = TwitterTrendsSource(test_mode=test_mode)
        articles = trends_source.get_novel_articles(1, existing_titles, similarity_threshold)

    # If no Twitter articles, fall back to Metaphor
    if not articles:
        metaphor_source = MetaphorSource(METAPHOR_QUERY)
        print(f"No Twitter articles, fetching from Metaphor about '{metaphor_source.query}'...")
        articles = metaphor_source.get_novel_articles(1, existing_titles, similarity_threshold)

    print(f"Found {len(articles)} articles to process")

    # Edit each article into a satirical story
    for i, article in enumerate(articles, 1):
        print(f"Generating satirical story {i} of {len(articles)} on {article.title}...")
        editor = StoryEditor()
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
