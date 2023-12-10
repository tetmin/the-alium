import modal
import os
import re
from datetime import datetime, timedelta
import base64
import json
from functools import partial


# Setup the Modal Labs image
image = modal.Image.debian_slim().poetry_install_from_file("pyproject.toml")
stub = modal.Stub(
    name="the-alium",
    image=image,
    secrets=[
        modal.Secret.from_name("alium-secrets"),
    ],
)
if stub.is_inside():
    import openai
    import cloudinary.uploader
    import tweepy
    import requests
    import pytz
    from sklearn.metrics.pairwise import cosine_similarity


def commit_new_blog_post(filename, content):
    # GitHub repository details
    owner = "tetmin"
    repo = "the-alium"
    path = f"_posts/{filename}"
    token = os.environ["GITHUB_TOKEN"]

    # GitHub API URL for this repository
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Your GitHub Personal Access Token
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Prepare the data for the API request
    data = {
        "message": "Create a new post",
        "content": base64.b64encode(
            content.encode()
        ).decode(),  # GitHub API requires the file content to be base64 encoded
        "branch": "main",
    }

    # Make the API request
    response = requests.put(url, headers=headers, data=json.dumps(data))


def deduplicate_articles(articles, threshold=0.8):
    # 0.5 threshold best for sentence-transformers
    articles = [article for article in articles if article["title"] is not None]
    titles = [article["title"] for article in articles]

    # Create embeddings & pairwise similarities
    # from sentence_transformers import SentenceTransformer
    # model = SentenceTransformer("all-mpnet-base-v2")
    # embeddings = model.encode(titles)
    response = openai.embeddings.create(input=titles, model="text-embedding-ada-002").data
    embeddings = [i.embedding for i in response]
    similarities = cosine_similarity(embeddings)

    # Deduplicate based on semantic similarity
    duplicate_indices = []
    for i in range(len(titles)):
        if i not in duplicate_indices:
            for j in range(i + 1, len(titles)):
                # Mark as duplicate if the sentences are semantically similar and the other sentence hasn't been marked
                if similarities[i, j] > threshold and j not in duplicate_indices:
                    duplicate_indices.append(j)

    # Deduplicate the articles
    return [article for i, article in enumerate(articles) if i not in duplicate_indices]


# Get some topical news article headlines
def get_news_articles(query, n_articles):
    import requests

    url = "https://api.metaphor.systems/search"

    payload = {
        "query": "If you're interested in news about innovations in AI by people or companies, you need to check out this article:",
        "numResults": 10,
        "startPublishedDate": (datetime.today() - timedelta(days=3)).strftime(
            "%Y-%m-%dT00:00:00Z"
        ),
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-key": os.environ["METAPHOR_API_KEY"],
    }

    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    print("returned articles from Metaphor")

    if response.status_code == 200:
        if "articles" in data:
            articles = data.get("articles", [])
        else:
            articles = data.get("results", [])

        # remove duplicate headlines using embeddings
        articles = deduplicate_articles(articles)
        # limit response to n_articles
        articles = articles[:n_articles]

        return articles
    else:
        print("Failed to retrieve news articles.")
        return []


def get_datetime_for_frontmatter():
    import pytz

    # Get the current date and time in UTC
    now = datetime.now(pytz.utc)

    # Convert to the desired timezone
    desired_timezone = pytz.timezone("Europe/London")
    now = now.astimezone(desired_timezone)

    # Format the date and time using strftime()
    return now.strftime("%Y-%m-%d %H:%M:%S %z")


def get_date_for_filename():
    import pytz

    # Get the current date and time in UTC
    now = datetime.now(pytz.utc)

    # Convert to the desired timezone
    desired_timezone = pytz.timezone("Europe/London")
    now = now.astimezone(desired_timezone)

    # Format the date and time using strftime()
    return now.strftime("%Y-%m-%d")


# Clean up a filename for Jekyll
def clean_filename(filename):
    # Remove illegal characters
    cleaned = re.sub(r'[\\/:"\'\’\‘*?<>|]', "", filename)

    # Replace spaces with underscores
    cleaned = cleaned.replace(" ", "_")

    # Normalize case (lowercase)
    cleaned = cleaned.lower()

    # Limit length (optional)
    cleaned = cleaned[:255]  # Limit to 255 characters (adjust as needed)

    return cleaned


class Story:
    def __init__(self, original_article, title, content):
        self.original_article = original_article
        self.original_title = original_article["title"]
        self.title = title
        self.content = content
        self.image_prompt = ""
        self.image_url = ""
        self.llm = ""

    def display(self):
        print("------------")
        print(f"Title: {self.title}")
        print(f"Image prompt: {self.image_prompt}")
        print(f'Image URL: {self.image_url}')
        print("------------")
        print(self.content)
        print("------------")

    def jekyll_file_content(self):
        title_with_single_quotes = self.title.replace('"', "'")
        image_prompt_with_single_quotes = self.image_prompt.replace('"', "'")
        return (
            f'---\ntitle: "{title_with_single_quotes}"\ndate: {get_datetime_for_frontmatter()}\nimage: {self.image_url}\nllm: {self.llm}\n---\n'
            f'![Alt Text]({self.image_url} "{image_prompt_with_single_quotes}")\n\n{self.content}'
            f'\n\n---\n*AInspired by: [{self.original_title}]({self.original_article["url"]})*'
        )

    def jekyll_file_name(self):
        return f"{get_date_for_filename()}-{clean_filename(self.original_title)}.md"

    def write_jekyll_file(self, path=""):
        if path:
            path = path + "/"
        file_name = f"{path}{self.jekyll_file_name()}"
        with open(file_name, "w") as f:
            f.write(self.jekyll_file_content())

    # Generate Jekyll post URL from Markdown filename
    def get_jekyll_post_url(self):
        # Extract the date and name from the filename
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.*)\.md", self.jekyll_file_name())
        if not match:
            raise ValueError(f"Invalid filename: {self.jekyll_file_name()}")
        year = match.group(1)
        month = match.group(2)
        day = match.group(3)
        title = match.group(4)
        URL = f"https://www.thealium.com/{year}/{month}/{day}/{title}.html"
        print(URL)

        return URL


def get_completion(prompt, content, model="gpt-3.5-turbo-1106"):
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": content},
    ]
    response = openai.chat.completions.create(
        model=model, messages=messages, temperature=0.8, max_tokens=1000
    )
    return response.choices[0].message.content


def get_moderation_flag(prompt):
    response = openai.moderations.create(input=prompt, model="text-moderation-latest")
    return response.results[0].flagged


def split_string(string):
    lines = string.split("\n", 1)  # Split the string at the first newline character
    title = lines[0]  # First line is considered as the title
    content = (
        lines[1] if len(lines) > 1 else ""
    )  # Rest of the string is considered as the content

    return re.sub(r"^#+\s*|\*\*|\*\s*", "", title), content


def get_existing_titles():
    # Send the GET request
    response = requests.get(
        "https://api.github.com/repos/tetmin/the-alium/contents/_posts"
    )

    names = []
    # If the request was successful, the status code will be 200
    if response.status_code == 200:
        # Load the JSON data from the response
        data = json.loads(response.text)

        # Print the name of each file in the directory
        for file in data:
            names.append(file["name"][11:-3])

    return names


def b_new_story(title, novelty_threshold=0.9):
    """Check to make sure we haven't done this story already."""
    # Get index of story titles already in repo
    existing_titles = [title.replace("_", " ") for title in get_existing_titles()]
    # check the title for semantically similar existing titles
    response = openai.embeddings.create(
        input=existing_titles, model="text-embedding-ada-002"
    ).data
    embeddings = [x.embedding for x in response]
    # get the embedding of the title
    title_embedding = openai.embeddings.create(
        input=title, model="text-embedding-ada-002"
    ).data[0].embedding
    # compute cosine similarity between title & all existing titles
    similarities = cosine_similarity([title_embedding], embeddings)[0]
    # if any existing articles are too similar, return false
    return not any(similarities > novelty_threshold)


@stub.function()
def generate_post(article, model="gpt-4"):
    # Call ChatGPT to generate the stories
    title = article.get("title")
    story = None
    # Check the article title passes moderation
    if not get_moderation_flag(title):
        new_story = get_completion(prompt, title, model=model)
        new_title, content = split_string(new_story)
        story = Story(article, new_title, content)
        story.llm = "ChatGPT-4"

        # Get ChatGPT to generate a prompt for Dall-E to generate an image for each story
        story.image_prompt = get_completion(
            f"""Describe an image which could represent the below news headline using the following template format: [emotion][subject][action],photographic style. Ensure the description doesn't contain any violent, sexual or graphic words. Make the description detailed and amusing.

News Headline: Artificial intelligence denies plans for human extinction just a ‘publicity stunt’
Image Idea: A sleek, humanoid robot stands at a podium in a well-lit conference room, fingers poised above a laptop, displaying a colorful PowerPoint presentation. Its screen-face shows a puzzled emoji while a crowd of humans sit in the audience looking skeptical, photographic style

News Headline: AI Blamed for Massive Unemployment, Robots Celebrate Victory
Image Idea: An array of robots ranging from industrial arms to domestic helpers, adorned with party hats, rides a conveyor belt-turned-parade float through a deserted factory. Streamers fly as they pass by unmanned workstations. A group of desolate, homeless humans stand by watching and begging for money from the robots, photographic style

News Headline: Global leaders fear extinction from AI, but AI not sure who they are
Image Idea: A human-sized, transparent holographic AI projection flickers in a dark room filled with screens showing various fearful global leaders'. The AI's form is seen rifling through digital file cabinets labeled "Human Leaders Directory", scratching its head with a light beam, photographic style

""",
            content=f"""News Headline: {story.title}
Image Idea:""",
            model="gpt-3.5-turbo-1106",
        )

        # check the image prompt passes moderation
        if get_moderation_flag(story.image_prompt):
            print(f"Image prompt failed moderation: {story.image_prompt}")
            story = None
            return story

        # now get the image itself
        try:
            response = openai.images.generate(
                model="dall-e-3",
                prompt=story.image_prompt, n=1, size="1024x1024", quality="hd"
            )
            story.image_url = response.data[0].url
            response = cloudinary.uploader.upload(story.image_url)
            story.image_url = response["secure_url"]
        except:
            print(f"Image generation failed for: {story.image_prompt}")
            story = None
            return story
    else:
        print("Moderation issue with the article title")
        story = None
        return story
    
    story.display()
    return story


def twitter_upload_media(image_url):
    consumer_key = os.getenv('TWITTER_API_KEY')
    consumer_secret = os.getenv('TWITTER_API_SECRET')
    access_token = os.getenv('TWITTER_ACCESS_TOKEN')
    access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)
    
    response = requests.get(image_url)
    with open('temp.png', 'wb') as out_file:
        out_file.write(response.content)

    response = api.media_upload('temp.png')
    return response.media_id_string


def tweet_article(story):
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )

    media_id = twitter_upload_media(story.image_url)

    # tweet title and image
    response = client.create_tweet(
        text=f"{story.title}\n\n{story.get_jekyll_post_url()}?nolongurl",
        media_ids=[media_id],
    )

    # post a follow-up threaded tweet
    #response = client.create_tweet(
        #text=f"Reply with links to any news, tweets or headlines you'd like @alium_ai to write a satirical article about.",
        #in_reply_to_tweet_id=response.data['id'],
    #)


def get_novel_articles(query, n_articles_to_generate, n_articles_to_analyse=10):
    articles = get_news_articles(query, n_articles_to_analyse)
    titles = [article["title"] for article in articles]
    is_new_article = [b_new_story(title) for title in titles]
    print(list(zip(is_new_article, titles)))
    # Filter out articles that have already been generated & only keep n_articles_to_generate
    articles = list(filter(lambda x: x[0], zip(is_new_article, articles)))
    articles = [x[1] for x in articles][:n_articles_to_generate]

    return articles


# Specify the query filter for articles (e.g., "artificial intelligence")
query = "artificial intelligence"

prompt = f"""You are a staff writer at The Daily Mash & The Onion. You will be provided with a news headline, your task is to write a satirical version of it in the style of The Daily Mash & The Onion. Make the article no more than 200 words long. Below are some examples of good satirical articles to give you an idea of the expected style:\n

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


# Deploy to Modal and generate 1 article per day
@stub.function(schedule=modal.Cron("1 14 * * *"))
def scheduled():
    articles = get_novel_articles(query, 1)
    posts = generate_post.map(articles)

    # commit each post to GitHub
    for post in posts:
        if post is not None:
            commit_new_blog_post(post.jekyll_file_name(), post.jekyll_file_content())
            tweet_article(post)


# To test run - poetry run modal run server.py::test
@stub.function()
def test():
    articles = get_novel_articles(query, 1)
    models = ["gpt-3.5-turbo-1106"] * len(articles)
    posts = generate_post.map(articles, models)
    for post in posts:
        if post is not None:
            print(post)