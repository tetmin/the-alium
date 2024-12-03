import base64
import functools
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import cloudinary.uploader
import dotenv
import litellm
import markdown
import modal
import numpy as np
import pytz
import requests
import tweepy
from jinja2 import Template
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, HttpUrl
from sklearn.metrics.pairwise import cosine_similarity
from together import Together
import io

dotenv.load_dotenv()
litellm.success_callback = ["athina"]  # For monitoring

# Initialize Modal Labs app for serverless deployment
image = (
    modal.Image.debian_slim()
    .poetry_install_from_file("pyproject.toml")
    .run_commands("playwright install --with-deps chromium")
)
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


def cache_articles(cache_file):
    """Decorator to cache API responses with different expiration times based on test mode"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            cache_path = Path(cache_file).with_suffix(".json")
            expiration = timedelta(days=365 if getattr(self, "_test_mode", False) else 1)

            # Load cache
            if cache_path.exists():
                try:
                    with cache_path.open("r") as f:
                        cache = json.load(f)
                        if datetime.fromisoformat(cache["timestamp"]) + expiration > datetime.now():
                            return [Article(title=a["title"], url=a["url"], data=a["data"]) for a in cache["data"]]
                except Exception as e:
                    print(f"Cache read error: {e}")
                    cache = {"timestamp": datetime.now().isoformat(), "data": []}

            # Get fresh data and cache it
            data = func(self, *args, **kwargs)
            try:
                cache_path.parent.mkdir(exist_ok=True)
                cache_data = [{"title": a.title, "url": str(a.url), "data": a.data} for a in data]
                with cache_path.open("w") as f:
                    json.dump({"timestamp": datetime.now().isoformat(), "data": cache_data}, f)
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
    image_prompt: str | None = None
    image_url: HttpUrl | None = None
    social_image: bytes | None = None
    blog_url: HttpUrl = ""
    llm: str = ""
    markdown: str = ""

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

    def get_screenshot(self, padding: int = 40) -> bytes:
        """Generate a screenshot of the story for social media."""
        # Strip frontmatter and convert content to HTML
        content = self.markdown.split("---", 2)[-1]
        html = markdown.markdown(content)
        template = Template("""
            <html>
            <head>
                <style>
                    body { 
                        margin: 0; 
                        font-family: -apple-system, system-ui, BlinkMacSystemFont;
                        background: white;
                        padding: {{ padding }}px;
                    }
                    .article {
                        max-width: {{ max_width }}px;
                        margin: 0 auto;
                    }
                    h1 { 
                        font-size: 48px;
                        line-height: 1.2;
                        margin-bottom: 30px;
                        color: #1a1a1a;
                    }
                    p {
                        font-size: 26px;
                        line-height: 1.6;
                        color: #333;
                    }
                    img {
                        width: 100%;  /* Changed from max-width to width */
                        height: auto;
                        margin: 15px 0;
                        display: block;  /* Ensures no inline spacing issues */
                    }
                </style>
            </head>
            <body>
                <div class="article">
                    <h1>{{ title }}</h1>
                    {{ content | safe }}
                </div>
            </body>
            </html>
        """)
        viewport_width = 1300
        max_width = viewport_width - (padding * 2)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": viewport_width, "height": 628})
            page.set_content(template.render(title=self.title, content=html, padding=padding, max_width=max_width))

            # Get the actual content height
            content_height = page.evaluate("""() => {
                const article = document.querySelector('.article');
                return article.getBoundingClientRect().height;
            }""")

            # Set viewport to match content plus padding
            page.set_viewport_size({"width": viewport_width, "height": int(content_height + (padding * 2))})
            image = page.screenshot(type="png")
            browser.close()
            return image

    def get_markdown(self) -> str:
        """Generate Jekyll-compatible markdown for the story"""
        self.title = self.title.replace('"', "'")
        self.image_prompt = self.image_prompt.replace('"', "'")

        now = datetime.now(pytz.utc).astimezone(pytz.timezone("Europe/London"))
        frontmatter_date = now.strftime("%Y-%m-%d %H:%M:%S %z")

        return (
            f'---\ntitle: "{self.title}"\ndate: {frontmatter_date}\nimage: {self.image_url}\nllm: {self.llm}\n---\n'
            f'![Alt Text]({self.image_url} "{self.image_prompt}")\n\n{self.content}'
            f"\n\n---\n*AInspired by: [{self.original_article.title}]({self.original_article.url})*"
        )


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
        story.blog_url = self._create_filename(story)
        return self.commit_new_blog_post(story.blog_url, story.markdown)

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

    def get_recent_article_titles(self, months_ago=3):
        response = requests.get(f"{self.base_url}/_posts", timeout=10)
        if response.status_code != 200:
            return []
        
        cutoff_date = datetime.now() - timedelta(days=months_ago * 30)
        filtered_titles = []
        
        for file in json.loads(response.text):
            try:
                # Extract date and title using regex for robustness
                match = re.match(r"(\d{4}-\d{2}-\d{2})-(.+?)\.(md|markdown)$", file["name"], re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if date >= cutoff_date:
                        title = match.group(2).replace('_', ' ')
                        filtered_titles.append(title)
            except ValueError:
                print(f"Invalid date format in filename: {file['name']}")
                continue
            
        return filtered_titles

    def _get_date_for_filename(self):
        now = datetime.now(pytz.utc).astimezone(pytz.timezone("Europe/London"))
        return now.strftime("%Y-%m-%d")

    def _clean_filename(self, filename):
        # First, replace special characters that cause URL issues
        cleaned = re.sub(r'[–—]', '-', filename)  # Convert em/en dashes to regular dashes
        cleaned = re.sub(r'[,]', '', cleaned)     # Remove commas
        # Then handle other invalid filename characters
        cleaned = re.sub(r'[\\/:*?"<>|]', '', cleaned)
        cleaned = cleaned.replace(" ", "_").lower()
        # Remove any remaining non-ASCII characters
        cleaned = "".join(c for c in cleaned if c.isascii())
        # Replace multiple underscores with single
        cleaned = re.sub(r'_+', '_', cleaned)
        # Remove leading/trailing underscores
        cleaned = cleaned.strip('_')
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

    def upload_media(self, image_url=None, image_bytes=None):
        if image_url:
            response = requests.get(image_url, timeout=10)
            file = io.BytesIO(response.content)
            response = self.api.media_upload(filename="story.png", file=file)
            return response.media_id_string
        elif image_bytes:
            file = io.BytesIO(image_bytes)
            response = self.api.media_upload(filename="story.png", file=file)
            return response.media_id_string
        return None

    def publish(self, story: Story):
        post_url = story.blog_url[:-3].replace("-", "/")
        post_url = f"https://www.thealium.com/{post_url}.html"

        # Try newspaper image style post first, fall back to regular image + URL
        if story.social_image:
            media_id = self.upload_media(image_bytes=story.social_image)
            response = self.client.create_tweet(text=story.title, media_ids=[media_id] if media_id else None)
        else:
            media_id = self.upload_media(image_url=story.image_url)
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

    @cache_articles(".cache/metaphor.json")
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

    def __init__(self, min_posts: int = 1000, test_mode: bool = False):
        self._test_mode = test_mode
        self.min_posts = min_posts
        # Initialize client regardless of test mode
        self.client = tweepy.Client(
            consumer_key=os.environ["TWITTER_API_KEY"],
            consumer_secret=os.environ["TWITTER_API_SECRET"],
            access_token=os.environ["X_PREMIUM_ACCESS_TOKEN"],
            access_token_secret=os.environ["X_PREMIUM_ACCESS_TOKEN_SECRET"],
        )

    def _parse_post_count(self, count_str: str) -> float:
        """Convert strings like '32K posts' or '1.9B posts' to numbers"""
        multipliers = {"K": 1000, "M": 1000000, "B": 1000000000}
        # Convert to upper first, then remove 'POSTS'
        count_str = count_str.upper().replace("POSTS", "").strip()

        if count_str[-1] in multipliers:
            number = float(count_str[:-1])
            return number * multipliers[count_str[-1]]
        return float(count_str)

    @cache_articles(".cache/twitter_trends.json")
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

    @cache_articles(".cache/twitter_mentions.json")
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

        # Generate markdown & screenshot
        story.markdown = story.get_markdown()
        story.social_image = story.get_screenshot()
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
        else:
            Path("story_example.png").write_bytes(story.social_image)


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
