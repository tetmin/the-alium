import base64
import json
import os
import re
from datetime import datetime, timedelta

import cloudinary.uploader
import modal
import numpy as np
import openai
import pytz
import requests
import tweepy
from pydantic import BaseModel, HttpUrl
from sklearn.metrics.pairwise import cosine_similarity

# Initialize Modal Labs app for serverless deployment
image = modal.Image.debian_slim().poetry_install_from_file("pyproject.toml")
app = modal.App(
    name="the-alium",
    image=image,
    secrets=[modal.Secret.from_name("alium-secrets")],
)

# Core prompt templates for story and image generation
STORY_PROMPT = """You are a staff writer at The Daily Mash & The Onion. You will be provided with a news headline, your task is to write a satirical version of it in the style of The Daily Mash & The Onion. Make the article no more than 200 words long. Below are some examples of good satirical articles to give you an idea of the expected style:\n

Article Example:
# Man who can’t spell basic words demands you take his opinions seriously
Roy Hobbs thinks he is a serious commentator on issues of the day, despite using horrible misspellings like ‘probebly’, ‘interlectuals’ and ‘definately’.\n
Friend Emma Bradford said: “Roy hasn’t grasped that if he thinks ‘restoraunt’ is spelt like that people might realise he’s not an expert on politics, economics or any other subject.\n
“He’s constantly writing ‘looser’ when he means ‘loser’ and ‘lightening’ when he means ‘lightning’. When it comes to ‘there’, ‘their’ and ‘they’re’ I think he just picks one at random.\n
“He’s always spouting pompous reactionary crap, so a typical post will be, ‘In my estimatoin, a bridge with France would be disasterous. We do not want closure intergration with the Continant.’\n
Hobbs said: “Criticising someone’s spelling is a pathetic attempt to undermine valid arguments such as my view that we should ban transsexuals from TV to stop children thinking it’s ‘cool’.”\n

Article Example:
# Human beats highly advanced computer at drinking
In a move designed to test the limits of technology, 30-year-old roofer Wayne Hayes took on Google’s DeepMind machine in a pint-for-pint battle.\n
A Google spokesman said: “Having recently beaten the human champion at the board game Go, we were eager to test DeepMind at something that Westerners can understand and respect.”\n
The AI machine was fitted with a specially-adapted USB cable with a pint glass on one end into which beer could be poured. However it broke after two pints, exploding in a shower of sparks as Stella Artois flooded its motherboard.\n
Hayes said: “I was confident from the start because that computer just didn’t have the red, bulky look of a drinker about it.\n
“They can build these machines that can do all sums and everything, but they’ll never take over from man if they can’t handle 15-16 pints of export lager.”\n
However the Google spokesman added: “We should have added a ‘piss port’ to allow DeepMind to expel fluids. Also I think a little slot that you tip pork scratchings into would help.”\n
"""
IMAGE_PROMPT_TEMPLATE = """Your goal is to take a satirical news headline and generate a similarly satirical image idea to go along with it in the news article. The image idea will be given to an artist or AI like Dall-E to create the image. Ensure the description doesn't contain any violent, sexual or graphic words. Make sure the resulting image idea is amusing and detailed. Below are some examples of good image ideas for headlines:\n\n

News Headline: Artificial intelligence denies plans for human extinction just a 'publicity stunt'\n
Image Idea: A sleek, humanoid robot stands at a podium in a well-lit conference room, fingers poised above a laptop, displaying a colorful PowerPoint presentation. Its screen-face shows a puzzled emoji while a crowd of humans sit in the audience looking skeptical, photographic style\n\n

News Headline: AI Blamed for Massive Unemployment, Robots Celebrate Victory\n
Image Idea: An array of robots ranging from industrial arms to domestic helpers, adorned with party hats, rides a conveyor belt-turned-parade float through a deserted factory. Streamers fly as they pass by unmanned workstations. A group of desolate, homeless humans stand by watching and begging for money from the robots, photographic style\n\n

News Headline: Global leaders fear extinction from AI, but AI not sure who they are\n
Image Idea: A human-sized, transparent holographic AI projection flickers in a dark room filled with screens showing various fearful global leaders'. The AI's form is seen rifling through digital file cabinets labeled "Human Leaders Directory", scratching its head with a light beam, photographic style\n\n

Important: You will respond only with the image idea, nothing else.
"""


# Handles GitHub repository operations (posting story markdown files and checking existing content)
class JekyllPublisher:
    def __init__(self):
        self.owner = "tetmin"
        self.repo = "the-alium"
        self.token = os.environ["GITHUB_TOKEN"]
        self.base_url = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}/contents"
        )
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

    def get_existing_story_titles(self):
        response = requests.get(f"{self.base_url}/_posts", timeout=10)
        if response.status_code == 200:
            data = json.loads(response.text)
            return [file["name"] for file in data]
        return []

    def get_recent_story_titles(self, months_ago=3):
        all_titles = self.get_existing_story_titles()
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
        auth = tweepy.OAuthHandler(
            os.environ["TWITTER_API_KEY"], os.environ["TWITTER_API_SECRET"]
        )
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
        return self.client.create_tweet(
            text=text, media_ids=[media_id] if media_id else None
        )


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
            "startPublishedDate": (datetime.today() - timedelta(days=3)).strftime(
                "%Y-%m-%dT00:00:00Z"
            ),
        }
        response = requests.post(url, json=payload, headers=self.headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            raw_articles = data.get("articles", data.get("results", []))
            articles = [
                Article.from_metaphor(article_data) for article_data in raw_articles
            ][:n_articles]
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

        sorted_indices = np.argsort(
            max_similarities
        )  # ascending order (least similar first)
        novel_articles = [
            articles[i]
            for i in sorted_indices
            if max_similarities[i] <= similarity_threshold
        ][:n_articles]
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
        return [
            item.embedding
            for item in openai.embeddings.create(
                input=texts, model="text-embedding-ada-002"
            ).data
        ]


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
        self.openai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def generate_story(self, article, model="gpt-4o", image_provider="together"):
        if self._get_moderation_flag(article.title):
            print(
                f"Moderation issue with the LLM proposed story title: {article.title}"
            )
            return None

        # Write the story
        story_content = self._get_completion(STORY_PROMPT, article.title, model=model)
        title, content = self._parse_completion(story_content)
        story = Story(original_article=article, title=title, content=content, llm=model)

        # Write the image prompt
        image_prompt = self._get_completion(
            IMAGE_PROMPT_TEMPLATE,
            f"News Headline: {story.title}\nImage Idea:",
            model="gpt-4o-mini",
        )
        if self._get_moderation_flag(image_prompt):
            print(f"Image prompt failed moderation: {image_prompt}")
            return None
        story.image_prompt = image_prompt

        # Generate the image
        story.image_url = self._generate_image(image_prompt)
        return story

    def _get_completion(self, prompt, content, model="gpt-4o-mini"):
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ]
        response = openai.chat.completions.create(
            model=model, messages=messages, temperature=0.8, max_tokens=1000
        )
        return response.choices[0].message.content

    def _parse_completion(self, completion):
        lines = completion.split("\n", 1)
        title = re.sub(r"^#+\s*|\*\*|\*\s*", "", lines[0])
        content = lines[1] if len(lines) > 1 else ""
        return title, content

    def _get_moderation_flag(self, prompt):
        response = openai.moderations.create(
            input=prompt, model="text-moderation-latest"
        )
        return response.results[0].flagged

    def _generate_image(self, prompt):
        response = openai.images.generate(
            model="dall-e-3", prompt=prompt, n=1, size="1024x1024", quality="hd"
        )
        return cloudinary.uploader.upload(response.data[0].url)["secure_url"]


# Specify the query filter for source articles (e.g., "artificial intelligence")
source = NewsSource("artificial intelligence")
editor = StoryEditor()
publisher = MultiPublisher()


# Main function to generate and publish satirical stories
@app.function(schedule=modal.Cron("1 14 * * *"))
def generate_and_publish_stories(test_mode: bool = False):
    # Log mode and fetch titles of existing stories written
    print("Running in test mode" if test_mode else "Running in production mode")
    print("Getting existing titles from past 3 months...")
    existing_titles = publisher.golden_source.get_recent_story_titles(months_ago=3)

    # Fetch and filter new news articles based on similarity to existing stories
    print(f"Fetching novel articles about '{source.query}'...")
    similarity_threshold = 0.95 if test_mode else 0.9  # Higher threshold in test mode
    articles = source.get_novel_articles(1, existing_titles, similarity_threshold)
    print(f"Found {len(articles)} novel articles")

    # Edit each article into a satirical story
    for i, article in enumerate(articles, 1):
        print(f"Generating satirical story {i} of {len(articles)}...")
        model = (
            "gpt-4o-mini" if test_mode else "gpt-4o"
        )  # Use smaller model in test mode
        story = editor.generate_story(article, model=model)
        print(story)

        # Publish if not in test mode and story generation succeeded
        if story and not test_mode:
            print("Publishing story...")
            publisher.publish_story(story)


# To test in local modal container without publishing: modal run server.py
# To publish manually: modal run server.py::generate_and_publish_stories
# To deploy on the schedule: modal deploy server.py
@app.local_entrypoint()
def main():
    generate_and_publish_stories.remote(test_mode=True)
